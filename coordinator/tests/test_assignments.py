"""Assigning and releasing from the area overview (architecture doc §3).

The service already refuses what it must; these tests are about the page turning those
refusals into something a person can read, and about not offering a control that will fail.
"""

import pytest
from django.urls import reverse

from accounts.models import User
from factories import LocalityFactory, TreeFactory, UserFactory, oversee
from trees.services import caretaker_of
from trees.tests.factories import assign

pytestmark = pytest.mark.django_db

OVERVIEW = reverse("coordinator:overview")


@pytest.fixture
def area():
    coordinator = UserFactory(role=User.Role.COORDINATOR)
    mine, theirs = LocalityFactory(name="Sierpc"), LocalityFactory(name="Płock")
    oversee(coordinator, mine)
    return coordinator, mine, theirs


def assign_url(tree):
    return reverse("coordinator:assign", kwargs={"tree_id": tree.pk})


def release_url(tree):
    return reverse("coordinator:release", kwargs={"tree_id": tree.pk})


class TestAssignFromThePage:
    def test_coordinator_assigns_and_is_told_so(self, client, area):
        coordinator, mine, _ = area
        tree, volunteer = TreeFactory(locality=mine), UserFactory(display_name="Anna")
        client.force_login(coordinator)

        response = client.post(assign_url(tree), {"volunteer": volunteer.pk}, follow=True)

        assert caretaker_of(tree) == volunteer
        assert any(m.level_tag == "success" for m in response.context["messages"])

    def test_a_tree_outside_the_area_is_a_message_not_a_crash(self, client, area):
        coordinator, _, theirs = area
        tree = TreeFactory(locality=theirs)
        client.force_login(coordinator)

        response = client.post(assign_url(tree), {"volunteer": UserFactory().pk}, follow=True)

        assert response.status_code == 200
        assert caretaker_of(tree) is None
        assert any(m.level_tag == "error" for m in response.context["messages"])

    def test_taken_tree_is_reported(self, client, area):
        coordinator, mine, _ = area
        tree = TreeFactory(locality=mine)
        assign(tree, UserFactory(display_name="Pierwsza"))
        client.force_login(coordinator)

        response = client.post(assign_url(tree), {"volunteer": UserFactory().pk}, follow=True)

        assert any(m.level_tag == "error" for m in response.context["messages"])
        assert caretaker_of(tree).display_name == "Pierwsza"

    def test_no_volunteer_chosen_is_handled(self, client, area):
        coordinator, mine, _ = area
        tree = TreeFactory(locality=mine)
        client.force_login(coordinator)

        response = client.post(assign_url(tree), {}, follow=True)

        assert response.status_code == 200
        assert caretaker_of(tree) is None

    def test_volunteer_cannot_use_the_endpoint(self, client, area):
        _, mine, _ = area
        tree = TreeFactory(locality=mine)
        client.force_login(UserFactory())

        assert client.post(assign_url(tree), {"volunteer": UserFactory().pk}).status_code == 403

    def test_anonymous_is_sent_to_login(self, client, area):
        _, mine, _ = area

        assert client.post(assign_url(TreeFactory(locality=mine))).status_code == 302

    def test_get_does_not_assign(self, client, area):
        coordinator, mine, _ = area
        tree = TreeFactory(locality=mine)
        client.force_login(coordinator)

        assert client.get(assign_url(tree)).status_code == 405


class TestReleaseFromThePage:
    def test_coordinator_releases(self, client, area):
        coordinator, mine, _ = area
        tree = TreeFactory(locality=mine)
        assign(tree, UserFactory())
        client.force_login(coordinator)

        client.post(release_url(tree), follow=True)

        assert caretaker_of(tree) is None

    def test_outside_the_area_is_refused(self, client, area):
        coordinator, _, theirs = area
        tree = TreeFactory(locality=theirs)
        assign(tree, UserFactory())
        client.force_login(coordinator)

        client.post(release_url(tree), follow=True)

        assert caretaker_of(tree) is not None

    def test_volunteer_cannot_use_the_endpoint(self, client, area):
        _, mine, _ = area
        tree = TreeFactory(locality=mine)
        assign(tree, UserFactory())
        client.force_login(UserFactory())

        assert client.post(release_url(tree)).status_code == 403


class TestControlsOnTheOverview:
    def test_tree_without_a_caretaker_offers_assignment(self, client, area):
        coordinator, mine, _ = area
        tree = TreeFactory(locality=mine)
        UserFactory(display_name="Wolna Anna")
        client.force_login(coordinator)

        content = client.get(OVERVIEW).content.decode()

        assert assign_url(tree) in content
        assert "Wolna Anna" in content, "Lista wolontariuszy do wyboru"

    def test_tree_with_a_caretaker_offers_release(self, client, area):
        coordinator, mine, _ = area
        tree = TreeFactory(locality=mine)
        assign(tree, UserFactory(display_name="Zajęta Anna"))
        client.force_login(coordinator)

        content = client.get(OVERVIEW).content.decode()

        assert release_url(tree) in content
        assert assign_url(tree) not in content, "Nie oferuj akcji, która i tak się nie uda"

    def test_inactive_volunteers_are_not_offered(self, client, area):
        """They could not act on the trees they were given."""
        coordinator, mine, _ = area
        TreeFactory(locality=mine)
        UserFactory(display_name="Zablokowany", is_active=False)
        client.force_login(coordinator)

        assert "Zablokowany" not in client.get(OVERVIEW).content.decode()
