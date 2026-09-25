"""Admin panel (spec §4): stats, thresholds, users, trees.

The panel is the only place where one click can change what every volunteer sees — or
lock the administrator out of their own system. Those two risks drive most of the tests
here; the rest check that the numbers on the dashboard match the database.
"""

from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from core.models import load_drought_config
from factories import LocalityFactory, TreeFactory, UserFactory
from panel.selectors import dashboard_stats
from trees.models import Tree, TreeSpecies
from trees.tests.factories import assign, water

pytestmark = pytest.mark.django_db

PAGES = ["panel:dashboard", "panel:thresholds", "panel:users", "panel:trees"]


@pytest.fixture
def admin(client):
    person = UserFactory(role=User.Role.ADMIN, display_name="Katarzyna Malinowska")
    client.force_login(person)
    return person


@pytest.fixture
def locality():
    return LocalityFactory(name="Sierpc")


class TestAccess:
    @pytest.mark.parametrize("name", PAGES)
    def test_admin_sees_the_panel(self, client, admin, name):
        assert client.get(reverse(name)).status_code == 200

    @pytest.mark.parametrize("name", PAGES)
    def test_volunteer_is_forbidden(self, client, name):
        client.force_login(UserFactory())

        assert client.get(reverse(name)).status_code == 403

    @pytest.mark.parametrize("name", PAGES)
    def test_guest_is_sent_to_login(self, client, name):
        response = client.get(reverse(name))

        assert response.status_code == 302 and reverse("accounts:login") in response.url

    def test_nav_link_only_for_admins(self, client, admin):
        assert ">Admin<" in client.get(reverse("trees:map")).content.decode()

        client.force_login(UserFactory())
        assert ">Admin<" not in client.get(reverse("trees:map")).content.decode()

    def test_api_requires_admin(self, client):
        client.force_login(UserFactory())

        assert client.get(reverse("admin-api:stats")).status_code == 403


class TestDashboardStats:
    def test_counts_match_the_database(self, locality, admin):
        volunteer = UserFactory()
        urgent = TreeFactory(locality=locality, status=Tree.Status.URGENT)
        TreeFactory(locality=locality, status=Tree.Status.OK)
        TreeFactory(locality=locality, lifecycle=Tree.Lifecycle.ARCHIVED)
        water(urgent, volunteer, days_ago=3)
        water(urgent, volunteer, days_ago=20)

        stats = dashboard_stats()

        assert stats["trees_total"] == 2
        assert stats["trees_archived"] == 1
        assert stats["by_status"] == {"OK": 1, "SOON": 0, "URGENT": 1}
        assert stats["waterings_7"] == 1
        assert stats["waterings_30"] == 2
        assert stats["volunteers_active"] == 1

    def test_trees_without_caretaker(self, locality, admin):
        tended = TreeFactory(locality=locality)
        TreeFactory(locality=locality)
        assign(tended, UserFactory())

        stats = dashboard_stats()

        assert stats["without_caretaker"] == 1

    def test_urgent_trees_are_listed_whoever_tends_them(self, locality, admin):
        lonely = TreeFactory(locality=locality, status=Tree.Status.URGENT, species="Lipa")
        tended = TreeFactory(locality=locality, status=Tree.Status.URGENT)
        assign(tended, UserFactory())

        listed = dashboard_stats()["needs_water"]

        assert {tree.pk for tree in listed} == {lonely.pk, tended.pk}
        assert {tree.has_caretaker for tree in listed} == {True, False}

    def test_watered_tree_without_a_caretaker_is_still_listed(self, locality, admin):
        """The case we used to miss: healthy, but nobody gets notified about it."""
        healthy = TreeFactory(locality=locality, status=Tree.Status.OK)
        tended = TreeFactory(locality=locality, status=Tree.Status.OK)
        assign(tended, UserFactory())

        assert [tree.pk for tree in dashboard_stats()["needs_caretaker"]] == [healthy.pk]

    def test_locality_row_counts_trees_without_a_caretaker(self, locality, admin):
        tended = TreeFactory(locality=locality)
        TreeFactory(locality=locality)
        assign(tended, UserFactory())

        (row,) = dashboard_stats()["localities"]

        assert row["total"] == 2 and row["orphans"] == 1

    def test_per_locality_breakdown(self, locality, admin):
        other = LocalityFactory(name="Studzieniec")
        TreeFactory(locality=locality, status=Tree.Status.URGENT)
        TreeFactory(locality=other, status=Tree.Status.OK)

        rows = {row["locality__name"]: row for row in dashboard_stats()["localities"]}

        assert rows["Sierpc"]["urgent"] == 1
        assert rows["Studzieniec"]["ok"] == 1

    def test_query_count_does_not_grow_with_trees(self, locality, admin, django_assert_num_queries):
        for _ in range(3):
            TreeFactory(locality=locality)
        with CaptureQueriesContext(connection) as captured:
            dashboard_stats()
        baseline = len(captured.captured_queries)

        for _ in range(9):
            TreeFactory(locality=locality)
        with django_assert_num_queries(baseline):
            dashboard_stats()


class TestThresholds:
    def payload(self, **overrides):
        return {
            "RAIN_WINDOW_DAYS": "5",
            "RAIN_THRESHOLD_MM": "10",
            "DAYS_SOON": "3",
            "DAYS_URGENT": "5",
        } | overrides

    def test_saving_updates_the_config_table(self, client, admin):
        client.post(reverse("panel:thresholds"), self.payload(DAYS_URGENT="8"))

        assert load_drought_config().days_urgent == 8

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("DAYS_URGENT", "3"),  # equal to DAYS_SOON
            ("DAYS_URGENT", "2"),  # below DAYS_SOON
            ("RAIN_WINDOW_DAYS", "0"),
            ("RAIN_THRESHOLD_MM", "-5"),
            ("DAYS_SOON", "nie liczba"),
        ],
    )
    def test_invalid_values_are_rejected(self, client, admin, field, value):
        response = client.post(reverse("panel:thresholds"), self.payload(**{field: value}))

        assert response.status_code == 200  # form redisplayed
        assert load_drought_config().days_urgent == 5  # unchanged

    def test_recompute_button_applies_them(self, client, admin, locality):
        long_ago = timezone.now() - timedelta(days=200)
        tree = TreeFactory(
            locality=locality,
            status=Tree.Status.OK,
            planted_on=long_ago.date(),
            created_at=long_ago,
        )
        water(tree, UserFactory(), days_ago=30)

        response = client.post(reverse("panel:recompute"), follow=True)

        tree.refresh_from_db()
        assert tree.status == Tree.Status.URGENT
        assert "Przeliczono" in response.content.decode()

    def test_api_get_and_put(self, client, admin):
        response = client.put(
            reverse("admin-api:config"),
            self.payload(DAYS_SOON="4", DAYS_URGENT="9"),
            content_type="application/json",
        )

        assert response.status_code == 200
        assert client.get(reverse("admin-api:config")).json()["DAYS_URGENT"] == "9"

    def test_api_validates_too(self, client, admin):
        response = client.put(
            reverse("admin-api:config"),
            self.payload(DAYS_URGENT="1"),
            content_type="application/json",
        )

        assert response.status_code == 400
        assert "DAYS_URGENT" in response.json()["errors"]


class TestUsers:
    def test_change_role(self, client, admin):
        person = UserFactory()

        client.post(
            reverse("panel:edit-user", kwargs={"user_id": person.pk}),
            {"role": User.Role.ADMIN, "is_active": "on"},
        )

        person.refresh_from_db()
        assert person.role == User.Role.ADMIN

    def test_deactivate_account(self, client, admin):
        person = UserFactory()

        client.post(
            reverse("panel:edit-user", kwargs={"user_id": person.pk}), {"role": person.role}
        )

        person.refresh_from_db()
        assert person.is_active is False

    def test_admin_cannot_demote_themselves(self, client, admin):
        """One click must not cost the project its only way into the panel."""
        response = client.post(
            reverse("panel:edit-user", kwargs={"user_id": admin.pk}),
            {"role": User.Role.VOLUNTEER, "is_active": "on"},
            follow=True,
        )

        admin.refresh_from_db()
        assert admin.role == User.Role.ADMIN
        assert "własnego konta" in response.content.decode()

    def test_admin_cannot_deactivate_themselves(self, client, admin):
        client.post(
            reverse("panel:edit-user", kwargs={"user_id": admin.pk}), {"role": User.Role.ADMIN}
        )

        admin.refresh_from_db()
        assert admin.is_active is True

    def test_api_patch_and_self_guard(self, client, admin):
        person = UserFactory()

        assert (
            client.patch(
                reverse("admin-api:user-detail", kwargs={"user_id": person.pk}),
                {"is_active": False},
                content_type="application/json",
            ).status_code
            == 200
        )
        assert (
            client.patch(
                reverse("admin-api:user-detail", kwargs={"user_id": admin.pk}),
                {"is_active": False},
                content_type="application/json",
            ).status_code
            == 400
        )

    def test_deactivated_user_loses_access(self, client, admin):
        person = UserFactory()
        client.post(
            reverse("panel:edit-user", kwargs={"user_id": person.pk}), {"role": person.role}
        )

        client.force_login(person)
        assert client.get(reverse("trees:my")).status_code == 302  # back to login


class TestTrees:
    @pytest.fixture
    def tree(self, locality):
        TreeSpecies.objects.get_or_create(name="Lipa drobnolistna")
        TreeSpecies.objects.get_or_create(name="Dąb szypułkowy")
        return TreeFactory(locality=locality, species="Lipa drobnolistna")

    def edit_url(self, tree):
        return reverse("panel:edit-tree", kwargs={"tree_id": tree.pk})

    def form_data(self, tree, **overrides):
        return {
            "species": tree.species,
            "species_other": "",
            "planted_on": tree.planted_on.isoformat(),
            "planted_by": tree.planted_by,
            "notes": tree.notes,
            "locality": str(tree.locality_id),
            "lifecycle": tree.lifecycle,
        } | overrides

    def test_edit_species_and_notes(self, client, admin, tree):
        client.post(
            self.edit_url(tree),
            self.form_data(tree, species="Dąb szypułkowy", notes="Podpora wymaga wymiany."),
        )

        tree.refresh_from_db()
        assert tree.species == "Dąb szypułkowy"
        assert tree.notes == "Podpora wymaga wymiany."

    def test_species_outside_the_catalogue_is_rejected(self, client, admin, tree):
        client.post(self.edit_url(tree), self.form_data(tree, species="Baobab afrykański"))

        tree.refresh_from_db()
        assert tree.species == "Lipa drobnolistna"

    def test_retired_species_stays_selectable_for_its_tree(self, client, admin, tree):
        """Editing notes must not force renaming a tree whose species was retired."""
        TreeSpecies.objects.filter(name="Lipa drobnolistna").update(is_active=False)

        client.post(self.edit_url(tree), self.form_data(tree, notes="Notatka"))

        tree.refresh_from_db()
        assert tree.notes == "Notatka" and tree.species == "Lipa drobnolistna"

    def test_archive_and_restore(self, client, admin, tree):
        url = reverse("panel:toggle-archive", kwargs={"tree_id": tree.pk})

        client.post(url)
        tree.refresh_from_db()
        assert tree.lifecycle == Tree.Lifecycle.ARCHIVED
        assert client.get(reverse("trees-api:list")).json() == []

        client.post(url)
        tree.refresh_from_db()
        assert tree.lifecycle == Tree.Lifecycle.ACTIVE
        assert len(client.get(reverse("trees-api:list")).json()) == 1

    def test_archived_tree_keeps_its_card(self, client, admin, tree):
        client.post(reverse("panel:toggle-archive", kwargs={"tree_id": tree.pk}))

        assert client.get(reverse("trees:card", kwargs={"tree_id": tree.pk})).status_code == 200

    def test_api_patch(self, client, admin, tree):
        response = client.patch(
            reverse("admin-api:tree-detail", kwargs={"tree_id": tree.pk}),
            {"lifecycle": "archived", "notes": "Uschło"},
            content_type="application/json",
        )

        tree.refresh_from_db()
        assert response.status_code == 200
        assert tree.lifecycle == Tree.Lifecycle.ARCHIVED and tree.notes == "Uschło"

    def test_list_filters(self, client, admin, tree, locality):
        # A different species, so the filtered list is told apart by name, not by luck.
        TreeFactory(locality=locality, status=Tree.Status.URGENT, species="Dąb szypułkowy")

        content = client.get(reverse("panel:trees"), {"status": "URGENT"}).content.decode()

        assert "Dąb szypułkowy" in content
        assert ">Lipa drobnolistna<" not in content


def test_stats_api_shape(client, admin, locality):
    TreeFactory(locality=locality, status=Tree.Status.URGENT)

    body = client.get(reverse("admin-api:stats")).json()

    assert body["trees_total"] == 1
    assert body["by_status"]["URGENT"] == 1
    assert isinstance(body["needs_water"], list)
    assert "species" in body["needs_water"][0]
    assert isinstance(body["needs_caretaker"], list)


def test_stats_api_has_no_personal_data(client, admin, locality):
    """Admin data is allowed to name people, but the stats endpoint has no reason to."""
    volunteer = UserFactory(display_name="Anna Kowalska", email="anna@tajne.example")
    tree = TreeFactory(locality=locality)
    water(tree, volunteer)

    content = client.get(reverse("admin-api:stats")).content.decode()

    assert "Anna Kowalska" not in content and "tajne.example" not in content
