"""In-app notices raised when a tree turns URGENT (UI doc §8.8, architecture doc §5.7).

Two properties carry the weight. They appear **once per drought episode** — the daily
recompute runs over every tree every morning, and a notice list that grows by one row per
tree per day is a list nobody opens twice. And a tree nobody looks after still reaches the
coordinators, because for that tree they are the only people who will hear about it at all.

Deliberately independent of `send_digests`: the one-e-mail-a-day rule shapes the mailbox, not
a list in the app, so nothing here may inherit that limit.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from accounts.models import User
from core.models import load_drought_config
from factories import LocalityFactory, TreeFactory, UserFactory, oversee
from notifications.models import Notification
from trees.models import Tree
from trees.services import recompute_all
from trees.tests.factories import assign, water
from weather.models import WeatherDaily

pytestmark = pytest.mark.django_db


def fill_dry_window(locality):
    """Rain rows at 0 mm for the whole window — a missing row is not a dry day (spec §5.1),
    so without these the algorithm rightly refuses to call it a drought."""
    yesterday = timezone.localdate() - timedelta(days=1)
    for offset in range(load_drought_config().rain_window_days):
        WeatherDaily.objects.get_or_create(
            locality=locality,
            day=yesterday - timedelta(days=offset),
            defaults={"precip_mm": Decimal("0.0")},
        )


def thirsty_tree(locality=None, caretaker=None):
    """Planted and registered long ago, never watered, standing in a dry locality."""
    locality = locality or LocalityFactory()
    long_ago = timezone.now() - timedelta(days=200)
    tree = TreeFactory(
        locality=locality,
        planted_on=long_ago.date(),
        created_at=long_ago,
        status=Tree.Status.OK,
    )
    fill_dry_window(locality)
    if caretaker:
        assign(tree, caretaker)
    return tree


def notices_for(user):
    return Notification.objects.filter(user=user)


def test_the_setup_really_causes_a_drought():
    """Guards the material itself. Without rain rows the algorithm rightly refuses to call a
    drought, and every test below would stay red no matter how correct the code was."""
    tree = thirsty_tree(caretaker=UserFactory())

    recompute_all()

    tree.refresh_from_db()
    assert tree.status == Tree.Status.URGENT


class TestWhoIsTold:
    def test_the_caretaker(self):
        tree = thirsty_tree()
        caretaker = UserFactory()
        assign(tree, caretaker)

        recompute_all()

        assert notices_for(caretaker).count() == 1
        assert notices_for(caretaker).get().tree == tree

    def test_a_tree_nobody_looks_after_reaches_the_coordinators(self):
        """For this tree they are the only ones who will hear about it at all."""
        locality = LocalityFactory()
        coordinator = UserFactory(role=User.Role.COORDINATOR)
        oversee(coordinator, locality)
        thirsty_tree(locality)

        recompute_all()

        assert notices_for(coordinator).count() == 1

    def test_the_coordinator_hears_about_a_tended_tree_too(self):
        locality = LocalityFactory()
        coordinator = UserFactory(role=User.Role.COORDINATOR)
        oversee(coordinator, locality)
        assign(thirsty_tree(locality), UserFactory())

        recompute_all()

        assert notices_for(coordinator).count() == 1

    def test_a_coordinator_of_another_area_is_not(self):
        coordinator = UserFactory(role=User.Role.COORDINATOR)
        oversee(coordinator, LocalityFactory(name="Płock"))
        thirsty_tree(LocalityFactory(name="Sierpc"))

        recompute_all()

        assert notices_for(coordinator).count() == 0

    def test_two_coordinators_both_hear(self):
        locality = LocalityFactory()
        first = UserFactory(role=User.Role.COORDINATOR)
        second = UserFactory(role=User.Role.COORDINATOR)
        oversee(first, locality)
        oversee(second, locality)
        thirsty_tree(locality)

        recompute_all()

        assert notices_for(first).count() == 1
        assert notices_for(second).count() == 1

    def test_an_unrelated_volunteer_hears_nothing(self):
        stranger = UserFactory()
        assign(thirsty_tree(), UserFactory())

        recompute_all()

        assert notices_for(stranger).count() == 0

    def test_an_inactive_caretaker_gets_nothing(self):
        tree = thirsty_tree()
        caretaker = UserFactory(is_active=False)
        assign(tree, caretaker)

        recompute_all()

        assert notices_for(caretaker).count() == 0


class TestOncePerEpisode:
    def test_a_tree_that_was_already_urgent_adds_nothing(self):
        """The recompute walks every tree every morning; the list must not grow with it."""
        tree = thirsty_tree()
        caretaker = UserFactory()
        assign(tree, caretaker)
        recompute_all()

        recompute_all()

        assert notices_for(caretaker).count() == 1

    def test_an_unread_notice_is_not_duplicated(self):
        tree = thirsty_tree()
        caretaker = UserFactory()
        assign(tree, caretaker)
        recompute_all()
        Tree.objects.filter(pk=tree.pk).update(status=Tree.Status.OK)

        recompute_all()

        assert notices_for(caretaker).count() == 1

    def test_after_reading_a_new_one_may_appear(self):
        """Read and still dry means the reminder has done its job and may come again."""
        tree = thirsty_tree()
        caretaker = UserFactory()
        assign(tree, caretaker)
        recompute_all()
        notices_for(caretaker).update(read_at=timezone.now())
        Tree.objects.filter(pk=tree.pk).update(status=Tree.Status.OK)

        recompute_all()

        assert notices_for(caretaker).count() == 2

    def test_another_tree_gets_its_own_notice(self):
        caretaker = UserFactory()
        locality = LocalityFactory()
        assign(thirsty_tree(locality), caretaker)
        assign(thirsty_tree(locality), caretaker)

        recompute_all()

        assert notices_for(caretaker).count() == 2


class TestWhenNothingHappens:
    def test_a_watered_tree_notifies_nobody(self):
        tree = thirsty_tree()
        caretaker = UserFactory()
        assign(tree, caretaker)
        water(tree, caretaker, days_ago=0)

        recompute_all()

        assert Notification.objects.count() == 0

    def test_a_dry_run_creates_nothing(self):
        assign(thirsty_tree(), UserFactory())

        recompute_all(save=False)

        assert Notification.objects.count() == 0

    def test_an_archived_tree_notifies_nobody(self):
        tree = thirsty_tree()
        assign(tree, UserFactory())
        Tree.objects.filter(pk=tree.pk).update(lifecycle=Tree.Lifecycle.ARCHIVED)

        recompute_all()

        assert Notification.objects.count() == 0


class TestCost:
    def test_no_query_per_tree(self, django_assert_num_queries):
        """The daily recompute touches every tree there is; this must not scale with it."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        locality = LocalityFactory()
        for _ in range(2):
            assign(thirsty_tree(locality), UserFactory())
        with CaptureQueriesContext(connection) as captured:
            recompute_all()
        baseline = len(captured.captured_queries)

        Notification.objects.all().delete()
        Tree.objects.update(status=Tree.Status.OK)
        for _ in range(6):
            assign(thirsty_tree(locality), UserFactory())

        with django_assert_num_queries(baseline):
            recompute_all()


class TestModel:
    def test_unread_by_default(self):
        tree = thirsty_tree()
        caretaker = UserFactory()
        assign(tree, caretaker)
        recompute_all()

        assert notices_for(caretaker).get().is_unread is True

    def test_newest_first(self):
        user = UserFactory()
        older = Notification.objects.create(user=user, tree=TreeFactory())
        newer = Notification.objects.create(user=user, tree=TreeFactory())
        Notification.objects.filter(pk=older.pk).update(
            created_at=timezone.now() - timedelta(days=1)
        )

        assert list(Notification.objects.all()) == [newer, older]

    def test_table_name_and_polish_labels(self):
        meta = Notification._meta

        assert meta.db_table == "notifications"
        assert meta.verbose_name == "powiadomienie"
