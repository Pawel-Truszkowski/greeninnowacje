"""The area overview (UI doc §8.9, mockup `poc/etap2-koordynator.html`).

Half of these tests are about what a coordinator must **not** see. The role exists to give
somebody authority over a patch of the map, and the only thing separating that from authority
over the whole map is a filter — so every selector is tested with a second locality present
that must never appear.
"""

from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from coordinator.selectors import area_stats, area_trees, area_volunteers
from factories import LocalityFactory, TreeFactory, UserFactory, oversee
from trees.models import Tree
from trees.tests.factories import assign, water

pytestmark = pytest.mark.django_db

URL = reverse("coordinator:overview")


@pytest.fixture
def area():
    """A coordinator over Sierpc, and a second locality that is none of their business."""
    coordinator = UserFactory(role=User.Role.COORDINATOR, display_name="Koordynator")
    mine = LocalityFactory(name="Sierpc")
    theirs = LocalityFactory(name="Płock")
    oversee(coordinator, mine)
    return coordinator, mine, theirs


class TestScopeOfTheTreeList:
    def test_only_trees_in_the_area(self, area):
        coordinator, mine, theirs = area
        here = TreeFactory(locality=mine)
        TreeFactory(locality=theirs)

        assert [tree.pk for tree in area_trees(coordinator)] == [here.pk]

    def test_archived_trees_are_left_out(self, area):
        coordinator, mine, _ = area
        TreeFactory(locality=mine, lifecycle=Tree.Lifecycle.ARCHIVED)

        assert list(area_trees(coordinator)) == []

    def test_most_urgent_first(self, area):
        coordinator, mine, _ = area
        ok = TreeFactory(locality=mine, status=Tree.Status.OK)
        urgent = TreeFactory(locality=mine, status=Tree.Status.URGENT)
        soon = TreeFactory(locality=mine, status=Tree.Status.SOON)

        order = [tree.pk for tree in area_trees(coordinator)]

        assert order == [urgent.pk, soon.pk, ok.pk]

    def test_two_localities_are_both_covered(self, area):
        coordinator, mine, theirs = area
        oversee(coordinator, theirs)
        TreeFactory(locality=mine)
        TreeFactory(locality=theirs)

        assert len(list(area_trees(coordinator))) == 2

    def test_admin_sees_everything(self, area):
        _, mine, theirs = area
        TreeFactory(locality=mine)
        TreeFactory(locality=theirs)

        assert len(list(area_trees(UserFactory(role=User.Role.ADMIN)))) == 2

    def test_coordinator_without_an_area_sees_nothing(self):
        TreeFactory()
        lonely = UserFactory(role=User.Role.COORDINATOR)

        assert list(area_trees(lonely)) == []

    def test_no_query_per_tree(self, area, django_assert_num_queries):
        coordinator, mine, _ = area
        for _ in range(2):
            TreeFactory(locality=mine)
        with CaptureQueriesContext(connection) as captured:
            [(tree.species, tree.locality.name) for tree in area_trees(coordinator)]
        baseline = len(captured.captured_queries)

        for _ in range(6):
            TreeFactory(locality=mine)
        with django_assert_num_queries(baseline):
            [(tree.species, tree.locality.name) for tree in area_trees(coordinator)]


class TestVolunteers:
    def test_only_volunteers_caring_for_trees_in_the_area(self, area):
        coordinator, mine, theirs = area
        ours = UserFactory(display_name="Nasza Anna")
        stranger = UserFactory(display_name="Obcy Jan")
        assign(TreeFactory(locality=mine), ours)
        assign(TreeFactory(locality=theirs), stranger)

        names = {row["display_name"] for row in area_volunteers(coordinator)}

        assert names == {"Nasza Anna"}

    def test_counts_trees_and_recent_waterings(self, area):
        coordinator, mine, _ = area
        volunteer = UserFactory(display_name="Anna")
        first, second = TreeFactory(locality=mine), TreeFactory(locality=mine)
        assign(first, volunteer)
        assign(second, volunteer)
        water(first, volunteer, days_ago=2)
        water(second, volunteer, days_ago=5)
        water(first, volunteer, days_ago=45)  # outside the 30-day window

        row = next(iter(area_volunteers(coordinator)))

        assert row["trees"] == 2
        assert row["waterings_30"] == 2

    def test_last_activity_is_the_newest_watering(self, area):
        coordinator, mine, _ = area
        volunteer = UserFactory()
        tree = TreeFactory(locality=mine)
        assign(tree, volunteer)
        water(tree, volunteer, days_ago=9)
        newest = water(tree, volunteer, days_ago=1)

        row = next(iter(area_volunteers(coordinator)))

        assert row["last_activity"] == newest.watered_at

    def test_volunteer_who_never_watered_still_appears(self, area):
        """Somebody who signed up and has not acted yet is exactly who a coordinator looks for."""
        coordinator, mine, _ = area
        assign(TreeFactory(locality=mine), UserFactory(display_name="Nowy"))

        row = next(iter(area_volunteers(coordinator)))

        assert row["display_name"] == "Nowy"
        assert row["waterings_30"] == 0
        assert row["last_activity"] is None

    def test_a_released_caretaker_drops_off_the_list(self, area):
        coordinator, mine, _ = area
        volunteer = UserFactory()
        tree = TreeFactory(locality=mine)
        assignment = assign(tree, volunteer)
        assignment.ended_at = timezone.now()
        assignment.save()

        assert list(area_volunteers(coordinator)) == []

    def test_no_query_per_volunteer(self, area, django_assert_num_queries):
        coordinator, mine, _ = area
        for _ in range(2):
            assign(TreeFactory(locality=mine), UserFactory())
        with CaptureQueriesContext(connection) as captured:
            list(area_volunteers(coordinator))
        baseline = len(captured.captured_queries)

        for _ in range(6):
            assign(TreeFactory(locality=mine), UserFactory())
        with django_assert_num_queries(baseline):
            list(area_volunteers(coordinator))


class TestStats:
    def test_counts_cover_the_area_only(self, area):
        coordinator, mine, theirs = area
        TreeFactory(locality=mine, status=Tree.Status.URGENT)
        TreeFactory(locality=mine, status=Tree.Status.SOON)
        TreeFactory(locality=theirs, status=Tree.Status.URGENT)

        stats = area_stats(coordinator)

        assert stats["trees_total"] == 2
        assert stats["by_status"][Tree.Status.URGENT] == 1

    def test_trees_without_a_caretaker_are_counted(self, area):
        coordinator, mine, _ = area
        assign(TreeFactory(locality=mine), UserFactory())
        TreeFactory(locality=mine)

        assert area_stats(coordinator)["without_caretaker"] == 1


class TestPage:
    def test_coordinator_sees_their_area(self, client, area):
        coordinator, mine, theirs = area
        here = TreeFactory(locality=mine, species="Jabłoń – Ligol")
        TreeFactory(locality=theirs, species="Grusza – Konferencja")
        client.force_login(coordinator)

        content = client.get(URL).content.decode()

        assert "Jabłoń – Ligol" in content
        assert "Grusza – Konferencja" not in content, "Cudza miejscowość nie może wyciec"
        assert reverse("trees:card", kwargs={"tree_id": here.pk}) in content

    def test_volunteer_table_is_rendered(self, client, area):
        coordinator, mine, _ = area
        assign(TreeFactory(locality=mine), UserFactory(display_name="Anna Kowalska"))
        client.force_login(coordinator)

        assert "Anna Kowalska" in client.get(URL).content.decode()

    def test_empty_area_is_explained_not_broken(self, client):
        client.force_login(UserFactory(role=User.Role.COORDINATOR))

        response = client.get(URL)

        assert response.status_code == 200
        assert "Brak przypisanej miejscowości" in response.content.decode()

    def test_navigation_links_to_the_area(self, client, area):
        coordinator, _, _ = area
        client.force_login(coordinator)

        assert URL in client.get(reverse("trees:map")).content.decode()

    def test_volunteer_does_not_see_the_link(self, client):
        client.force_login(UserFactory())

        assert URL not in client.get(reverse("trees:map")).content.decode()


class TestDashboardStatsStaysGlobal:
    """The panel's own numbers must not change because the coordinator reuses them."""

    def test_without_an_argument_nothing_is_filtered(self, area):
        from panel.selectors import dashboard_stats

        _, mine, theirs = area
        TreeFactory(locality=mine)
        TreeFactory(locality=theirs)

        assert dashboard_stats()["trees_total"] == 2

    def test_with_locality_ids_it_narrows(self, area):
        from panel.selectors import dashboard_stats

        _, mine, theirs = area
        TreeFactory(locality=mine)
        TreeFactory(locality=theirs)

        assert dashboard_stats(locality_ids=[mine.pk])["trees_total"] == 1


def test_recent_window_is_thirty_days():
    """The volunteer table says „Podlania (30 dni)" — the number has to mean that."""
    from panel.selectors import ACTIVITY_DAYS

    assert ACTIVITY_DAYS == 30
    assert timedelta(days=ACTIVITY_DAYS).days == 30
