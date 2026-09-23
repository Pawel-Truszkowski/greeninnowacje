"""Watering, caretaker assignment and 'Moje drzewa' (spec §4, volunteer endpoints)."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from factories import TreeFactory, UserFactory
from trees.models import Assignment, Tree, Watering
from trees.tests.factories import assign, water

pytestmark = pytest.mark.django_db


def api_water(tree):
    return reverse("trees-api:waterings", kwargs={"tree_id": tree.pk})


def page_water(tree):
    return reverse("trees:water", kwargs={"tree_id": tree.pk})


@pytest.fixture
def volunteer(client):
    user = UserFactory()
    client.force_login(user)
    return user


class TestWateringApi:
    def test_records_watering_and_returns_new_status(self, client, volunteer):
        tree = TreeFactory(status=Tree.Status.URGENT)
        water(tree, volunteer, days_ago=40)

        response = client.post(api_water(tree))

        assert response.status_code == 201
        assert response.json()["status"] == Tree.Status.OK
        tree.refresh_from_db()
        assert tree.status == Tree.Status.OK
        assert tree.waterings.count() == 2

    def test_server_owns_time_and_author(self, client, volunteer):
        """Spec §4: no body — the client cannot backdate a watering or credit someone else."""
        other = UserFactory()
        tree = TreeFactory()

        client.post(
            api_water(tree),
            {"watered_at": "2020-01-01T00:00:00Z", "user": str(other.pk)},
            content_type="application/json",
        )

        watering = Watering.objects.get(tree=tree)
        assert watering.user == volunteer
        assert watering.watered_at.date() == timezone.localdate()

    def test_anonymous_cannot_water(self, client):
        tree = TreeFactory()
        assert client.post(api_water(tree)).status_code == 403
        assert not Watering.objects.exists()

    def test_archived_tree_cannot_be_watered(self, client, volunteer):
        tree = TreeFactory(lifecycle=Tree.Lifecycle.ARCHIVED)
        assert client.post(api_water(tree)).status_code == 404

    def test_rate_limited(self, client, volunteer, settings):
        settings.WATERING_RATE_LIMIT = "3/m"
        tree = TreeFactory()

        statuses = [client.post(api_water(tree)).status_code for _ in range(4)]

        assert statuses == [201, 201, 201, 429]
        assert Watering.objects.count() == 3

    def test_history_stays_append_only(self, client, volunteer):
        """Watering twice adds a second row rather than updating the first (spec §3)."""
        tree = TreeFactory()
        client.post(api_water(tree))
        client.post(api_water(tree))

        assert Watering.objects.filter(tree=tree).count() == 2


class TestWateringPage:
    def test_button_waters_and_thanks(self, client, volunteer):
        tree = TreeFactory()

        response = client.post(page_water(tree), follow=True)

        assert "Dziękujemy! Drzewo zostało podlane 🌱" in response.content.decode()
        assert Watering.objects.filter(tree=tree, user=volunteer).exists()

    def test_watering_from_list_returns_to_list(self, client, volunteer):
        tree = TreeFactory()
        assign(tree, volunteer)

        response = client.post(page_water(tree), {"from": "list"})

        assert response.url == reverse("trees:my")

    def test_anonymous_is_sent_to_login(self, client):
        tree = TreeFactory()
        response = client.post(page_water(tree))
        assert response.status_code == 302 and reverse("accounts:login") in response.url


class TestCaretaker:
    def test_volunteer_can_take_a_free_tree(self, client, volunteer):
        tree = TreeFactory()

        response = client.post(reverse("trees-api:assign", kwargs={"tree_id": tree.pk}))

        assert response.status_code == 201
        assert Assignment.objects.filter(tree=tree, user=volunteer, ended_at=None).exists()

    def test_taken_tree_returns_409(self, client, volunteer):
        tree = TreeFactory()
        assign(tree, UserFactory())

        response = client.post(reverse("trees-api:assign", kwargs={"tree_id": tree.pk}))

        assert response.status_code == 409

    def test_release_own_assignment(self, client, volunteer):
        tree = TreeFactory()
        assign(tree, volunteer)

        response = client.post(reverse("trees-api:unassign", kwargs={"tree_id": tree.pk}))

        assert response.status_code == 204
        assert not Assignment.objects.filter(tree=tree, ended_at=None).exists()

    def test_cannot_release_somebody_elses_assignment(self, client, volunteer):
        tree = TreeFactory()
        assign(tree, UserFactory())

        response = client.post(reverse("trees-api:unassign", kwargs={"tree_id": tree.pk}))

        assert response.status_code == 400
        assert Assignment.objects.filter(tree=tree, ended_at=None).exists()

    def test_tree_can_be_taken_again_after_release(self, client, volunteer):
        tree = TreeFactory()
        previous = assign(tree, UserFactory())
        previous.ended_at = timezone.now()
        previous.save()

        assert (
            client.post(reverse("trees-api:assign", kwargs={"tree_id": tree.pk})).status_code == 201
        )


class TestMyTrees:
    def test_sorted_by_urgency_then_oldest_watering(self, client, volunteer):
        ok = TreeFactory(status=Tree.Status.OK)
        soon = TreeFactory(status=Tree.Status.SOON)
        urgent_recent = TreeFactory(status=Tree.Status.URGENT)
        urgent_old = TreeFactory(status=Tree.Status.URGENT)
        for tree in (ok, soon, urgent_recent, urgent_old):
            assign(tree, volunteer)
        water(urgent_recent, volunteer, days_ago=6)
        water(urgent_old, volunteer, days_ago=20)

        body = client.get(reverse("me-api:trees")).json()

        assert [tree["id"] for tree in body] == [
            str(urgent_old.pk),
            str(urgent_recent.pk),
            str(soon.pk),
            str(ok.pk),
        ]

    def test_never_watered_tree_comes_first_within_its_status(self, client, volunteer):
        watered = TreeFactory(status=Tree.Status.URGENT)
        never = TreeFactory(status=Tree.Status.URGENT)
        assign(watered, volunteer)
        assign(never, volunteer)
        water(watered, volunteer, days_ago=10)

        body = client.get(reverse("me-api:trees")).json()

        assert [tree["id"] for tree in body] == [str(never.pk), str(watered.pk)]

    def test_only_my_active_assignments(self, client, volunteer):
        mine = TreeFactory()
        assign(mine, volunteer)
        assign(TreeFactory(), UserFactory())
        archived = TreeFactory(lifecycle=Tree.Lifecycle.ARCHIVED)
        assign(archived, volunteer)

        body = client.get(reverse("me-api:trees")).json()

        assert [tree["id"] for tree in body] == [str(mine.pk)]

    def test_page_shows_empty_state(self, client, volunteer):
        content = client.get(reverse("trees:my")).content.decode()
        assert "Nie opiekujesz się jeszcze żadnym drzewem" in content

    def test_page_lists_trees(self, client, volunteer):
        tree = TreeFactory(species="Jarząb pospolity")
        assign(tree, volunteer)
        water(tree, volunteer, days_ago=1)

        content = client.get(reverse("trees:my")).content.decode()

        assert "Jarząb pospolity" in content and "podlane wczoraj" in content


class TestExtendedCard:
    def test_logged_in_card_shows_names(self, client, volunteer):
        tree = TreeFactory()
        waterer = UserFactory(display_name="Marta Wiśniewska")
        water(tree, waterer)
        assign(tree, UserFactory(display_name="Anna Kowalska"))

        body = client.get(reverse("trees-api:detail", kwargs={"tree_id": tree.pk})).json()

        assert body["waterings"][0]["by"] == "Marta Wiśniewska"
        assert body["caretaker"] == "Anna Kowalska"

    def test_public_card_still_hides_them(self, client, volunteer):
        tree = TreeFactory()
        water(tree, UserFactory(display_name="Marta Wiśniewska"))

        content = client.get(reverse("trees-api:public", kwargs={"tree_id": tree.pk})).content

        assert b"Marta" not in content

    def test_anonymous_cannot_read_extended_card(self, client):
        tree = TreeFactory()
        url = reverse("trees-api:detail", kwargs={"tree_id": tree.pk})
        assert client.get(url).status_code == 403

    def test_page_shows_watering_button_only_when_logged_in(self, client, volunteer):
        tree = TreeFactory()
        url = reverse("trees:card", kwargs={"tree_id": tree.pk})

        assert "Oznacz jako podlane" in client.get(url).content.decode()

        client.logout()
        assert "Oznacz jako podlane" not in client.get(url).content.decode()


class TestImmediateRecompute:
    def test_status_changes_without_waiting_for_cron(self, client, volunteer):
        """Spec §6.2: watering today recomputes that tree's status straight away."""
        tree = TreeFactory(status=Tree.Status.URGENT)
        water(tree, volunteer, days_ago=30)
        assert Tree.objects.get(pk=tree.pk).status == Tree.Status.URGENT

        client.post(api_water(tree))

        assert Tree.objects.get(pk=tree.pk).status == Tree.Status.OK

    def test_rain_keeps_status_ok_after_old_watering(self, client, volunteer, settings):
        from decimal import Decimal

        from weather.models import WeatherDaily

        tree = TreeFactory()
        water(tree, volunteer, days_ago=30)
        today = timezone.localdate()
        for offset in range(3):
            WeatherDaily.objects.create(
                locality=tree.locality, day=today - timedelta(days=offset), precip_mm=Decimal("4")
            )

        from trees.services import recompute_tree_status

        assert recompute_tree_status(tree) == Tree.Status.OK
