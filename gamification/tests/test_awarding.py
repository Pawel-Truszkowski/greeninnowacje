"""Handing out badges: from the tree services, once, and only for what really happened.

`award_badges` runs inside the transaction of the action that earned the badge — the same
rule as the activity log — so a refused operation awards nothing. Stats come from the
domain tables, so a badge also reflects work done before this feature existed.
"""

import io
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from factories import LocalityFactory, TreeFactory, UserFactory, oversee
from gamification.models import UserBadge
from gamification.rules import BADGES_BY_CODE
from gamification.selectors import user_stats
from gamification.services import (
    NAMED_IN_TOAST,
    award_badges,
    new_badges_message,
    take_unseen,
)
from trees.models import Assignment, Tree, Watering
from trees.services import (
    CaretakerConflict,
    DuplicateTree,
    add_photo,
    assign_caretaker,
    assign_caretaker_for,
    delete_photo,
    record_watering,
    register_tree,
)
from trees.tests.factories import assign, water

pytestmark = pytest.mark.django_db


def codes(user):
    return set(UserBadge.objects.filter(user=user).values_list("code", flat=True))


def jpeg():
    buffer = io.BytesIO()
    Image.new("RGB", (900, 600), "green").save(buffer, "JPEG")
    return SimpleUploadedFile("zdjecie.jpg", buffer.getvalue(), content_type="image/jpeg")


@pytest.fixture
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


class TestStats:
    def test_watering_one_tree_twice_a_day_is_one_tree_day(self, tree, user):
        water(tree, user)
        water(tree, user)
        water(TreeFactory(), user)
        water(tree, user, days_ago=1)

        stats = user_stats(user)

        assert stats.tree_days == 3
        assert len(stats.watering_days) == 2

    def test_days_are_local_days(self, tree, user):
        """23:30 and 00:30 local time are two days, although in UTC they share a date."""
        with timezone.override("Europe/Warsaw"):
            midnight = timezone.make_aware(datetime(2026, 7, 10))
            for minutes in (-30, 30):
                Watering.objects.create(
                    tree=tree, user=user, watered_at=midnight + timedelta(minutes=minutes)
                )

            assert len(user_stats(user).watering_days) == 2

    def test_care_counts_each_tree_once_and_the_longest_stint(self, tree, user):
        now = timezone.now()
        Assignment.objects.create(
            tree=tree,
            user=user,
            started_at=now - timedelta(days=50),
            ended_at=now - timedelta(days=40),
        )
        Assignment.objects.create(tree=tree, user=user, started_at=now - timedelta(days=12))

        stats = user_stats(user)

        assert stats.trees_cared == 1
        assert stats.longest_care_days == 12

    def test_archived_trees_still_count_as_registered(self, user):
        TreeFactory(created_by=user, lifecycle=Tree.Lifecycle.ARCHIVED)

        assert user_stats(user).registered == 1


def water_at(tree, user, hour, *, day=None, status=None):
    """A watering at a local hour (Europe/Warsaw is the project's zone)."""
    day = day or timezone.localdate() - timedelta(days=1)
    moment = timezone.make_aware(datetime.combine(day, datetime.min.time()).replace(hour=hour))
    return Watering.objects.create(tree=tree, user=user, watered_at=moment, tree_status=status)


class TestNewStats:
    def test_morning_and_evening_are_local_hours(self, tree, user):
        water_at(tree, user, 7)
        water_at(tree, user, 8)  # same tree-day: counts once
        water_at(TreeFactory(), user, 20)
        water_at(TreeFactory(), user, 13)

        stats = user_stats(user)

        assert (stats.morning_tree_days, stats.evening_tree_days) == (1, 1)

    def test_rescues_count_urgent_tree_days(self, tree, user):
        water_at(tree, user, 10, status=Tree.Status.URGENT)
        water_at(tree, user, 11, status=Tree.Status.OK)
        water_at(TreeFactory(), user, 10, status=Tree.Status.SOON)
        water_at(TreeFactory(), user, 10)  # recorded before the column existed

        assert user_stats(user).rescue_tree_days == 1

    def test_species_ignore_case_and_spaces(self, user):
        for name in ("Lipa", " lipa ", "Klon", "Dąb"):
            water(TreeFactory(species=name), user)

        assert user_stats(user).species == 3

    def test_localities(self, user):
        here, there = LocalityFactory(), LocalityFactory()
        water(TreeFactory(locality=here), user)
        water(TreeFactory(locality=here), user)
        water(TreeFactory(locality=there), user)

        assert user_stats(user).localities == 2

    def test_neighbour_is_a_tree_neither_registered_nor_cared_for(self, user):
        own = TreeFactory(created_by=user)
        cared = TreeFactory()
        assign(cared, user)
        stranger = TreeFactory()
        for tree in (own, cared, stranger):
            water(tree, user)

        assert user_stats(user).neighbour_tree_days == 1

    def test_care_counts_at_the_moment_of_watering(self, tree, user):
        """Watered while it was someone else's job, taken into care later: still a neighbour."""
        water(tree, user, days_ago=5)
        assign(tree, user)
        water(tree, user)

        assert user_stats(user).neighbour_tree_days == 1

    def test_care_that_ended_makes_it_a_neighbour_again(self, tree, user):
        now = timezone.now()
        Assignment.objects.create(
            tree=tree,
            user=user,
            started_at=now - timedelta(days=20),
            ended_at=now - timedelta(days=10),
        )
        water(tree, user, days_ago=15)
        water(tree, user, days_ago=2)

        assert user_stats(user).neighbour_tree_days == 1


class TestFromServices:
    def test_watering_stores_the_status_the_map_showed(self, tree, user):
        Tree.objects.filter(pk=tree.pk).update(status=Tree.Status.URGENT)
        tree.refresh_from_db()

        watering, _ = record_watering(tree, user)

        watering.refresh_from_db()
        assert watering.tree_status == Tree.Status.URGENT
        assert "rescuer" in codes(user)

    def test_watering_a_fine_tree_is_no_rescue(self, tree, user):
        watering, _ = record_watering(tree, user)

        assert watering.tree_status == Tree.Status.OK
        assert "rescuer" not in codes(user)

    def test_first_watering_earns_first_drop(self, tree, user):
        """`tree` is somebody else's and nobody's in care — so it is a neighbour's help, too."""
        record_watering(tree, user)

        assert codes(user) == {"first_drop", "good_neighbour"}

    def test_taking_care_earns_caretaker(self, tree, user):
        assign_caretaker(tree, user)

        assert "caretaker" in codes(user)

    def test_registering_earns_planter(self, user):
        register_tree(
            user, locality_name="Sierpc", lat=Decimal("52.88"), lng=Decimal("19.66"), species="Lipa"
        )

        assert "planter" in codes(user)

    def test_a_photo_earns_chronicler(self, media_root, user):
        add_photo(TreeFactory(created_by=user), user, jpeg())

        assert "chronicler" in codes(user)

    def test_coordinator_assignment_rewards_the_caretaker(self, user):
        coordinator = UserFactory(role="coordinator")
        locality = LocalityFactory()
        oversee(coordinator, locality)

        assign_caretaker_for(TreeFactory(locality=locality), user, by=coordinator)

        assert "caretaker" in codes(user)
        assert "caretaker" not in codes(coordinator)


class TestRefusedActions:
    def test_a_lost_caretaker_race_awards_nothing(self, tree, user):
        assign(tree, UserFactory())

        with pytest.raises(CaretakerConflict):
            assign_caretaker(tree, user)

        assert codes(user) == set()

    def test_a_refused_duplicate_awards_nothing(self, user):
        point = {"lat": Decimal("52.880000"), "lng": Decimal("19.660000")}
        TreeFactory(**point)

        with pytest.raises(DuplicateTree):
            register_tree(user, locality_name="Sierpc", species="Lipa", **point)

        assert codes(user) == set()

    def test_watering_an_archived_tree_awards_nothing(self, client, user):
        tree = TreeFactory(lifecycle=Tree.Lifecycle.ARCHIVED)
        client.force_login(user)

        response = client.post(reverse("trees:water", kwargs={"tree_id": tree.pk}))

        assert response.status_code == 404
        assert codes(user) == set()


class TestAwarding:
    def test_is_idempotent(self, tree, user):
        water(tree, user)

        assert award_badges(user) == ["first_drop", "good_neighbour"]
        assert award_badges(user) == []
        assert UserBadge.objects.filter(user=user).count() == 2

    def test_counts_work_done_before_the_feature(self, user):
        """Waterings from before this release count: the stats read the permanent tables."""
        for days_ago in range(7):
            water(TreeFactory(), user, days_ago=days_ago)

        award_badges(user)

        assert {"first_drop", "week_streak"} <= codes(user)

    def test_a_badge_stays_when_its_reason_goes(self, media_root, user):
        photo = add_photo(TreeFactory(created_by=user), user, jpeg())

        delete_photo(photo, user)
        award_badges(user)

        assert "chronicler" in codes(user)

    def test_anonymous_gets_nothing(self):
        from django.contrib.auth.models import AnonymousUser

        assert award_badges(AnonymousUser()) == []
        assert award_badges(None) == []


class TestUnseen:
    def test_returns_new_badges_once(self, tree, user):
        record_watering(tree, user)

        assert {badge.code for badge in take_unseen(user)} == {"first_drop", "good_neighbour"}
        assert take_unseen(user) == []

    def test_message_names_one_badge(self):
        message = new_badges_message([BADGES_BY_CODE["first_drop"]])

        assert "Nowa odznaka" in message
        assert "Pierwsza kropla" in message

    def test_several_badges_make_one_message(self):
        message = new_badges_message([BADGES_BY_CODE["planter"], BADGES_BY_CODE["chronicler"]])

        assert "Nowe odznaki" in message
        assert "Sadownik" in message and "Kronikarz" in message

    def test_a_large_batch_is_counted_not_listed(self):
        """Past work unlocking a pile of new badges at once — one short toast."""
        batch = list(BADGES_BY_CODE.values())[: NAMED_IN_TOAST + 2]

        message = new_badges_message(batch)

        assert f"Masz {len(batch)} nowych odznak" in message
        assert batch[0].name not in message

    @pytest.mark.parametrize(
        ("count", "word"),
        [(4, "nowe odznaki"), (5, "nowych odznak"), (12, "nowych odznak"),
         (22, "nowe odznaki"), (25, "nowych odznak")],
    )  # fmt: skip
    def test_polish_plural(self, count, word):
        badge = BADGES_BY_CODE["first_drop"]

        assert f"Masz {count} {word}!" in new_badges_message([badge] * count)

    def test_up_to_the_limit_badges_are_named(self):
        batch = list(BADGES_BY_CODE.values())[:NAMED_IN_TOAST]

        message = new_badges_message(batch)

        assert all(badge.name in message for badge in batch)

    def test_no_badges_no_message(self):
        assert new_badges_message([]) is None
