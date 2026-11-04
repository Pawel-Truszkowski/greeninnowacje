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
from gamification.services import award_badges, new_badges_message, take_unseen
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


class TestFromServices:
    def test_first_watering_earns_first_drop(self, tree, user):
        record_watering(tree, user)

        assert codes(user) == {"first_drop"}

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

        assert award_badges(user) == ["first_drop"]
        assert award_badges(user) == []
        assert UserBadge.objects.filter(user=user).count() == 1

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

        assert [badge.code for badge in take_unseen(user)] == ["first_drop"]
        assert take_unseen(user) == []

    def test_message_names_one_badge(self):
        message = new_badges_message([BADGES_BY_CODE["first_drop"]])

        assert "Nowa odznaka" in message
        assert "Pierwsza kropla" in message

    def test_several_badges_make_one_message(self):
        message = new_badges_message([BADGES_BY_CODE["planter"], BADGES_BY_CODE["chronicler"]])

        assert "Nowe odznaki" in message
        assert "Sadownik" in message and "Kronikarz" in message

    def test_no_badges_no_message(self):
        assert new_badges_message([]) is None
