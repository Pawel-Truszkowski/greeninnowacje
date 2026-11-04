"""Which trees a person registered and looks after — the users tab (Greenowacje feedback).

„Posadził" maps to `Tree.created_by`: the account that registered the tree. `planted_by` is
free text and may name somebody without an account, so it is shown, never joined on.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from activity.models import ActivityEvent
from factories import TreeFactory, UserFactory
from panel.selectors import user_trees
from trees.models import Assignment, Tree
from trees.tests.factories import assign, water

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin(client):
    person = UserFactory(role=User.Role.ADMIN)
    client.force_login(person)
    return person


@pytest.fixture
def anna():
    return UserFactory(display_name="Anna Kowalska")


def ended(tree, user, days_ago):
    return Assignment.objects.create(
        tree=tree,
        user=user,
        started_at=timezone.now() - timedelta(days=days_ago + 30),
        ended_at=timezone.now() - timedelta(days=days_ago),
    )


class TestSelector:
    def test_splits_registered_current_and_past_care(self, anna):
        registered = TreeFactory(created_by=anna, species="Lipa")
        cared = TreeFactory(species="Dąb")
        assign(cared, anna)
        former = TreeFactory(species="Klon")
        ended(former, anna, days_ago=5)
        TreeFactory()  # somebody else's, must not appear

        data = user_trees(anna)

        assert [tree.pk for tree in data["registered"]] == [registered.pk]
        assert [tree.pk for tree in data["caring"]] == [cared.pk]
        assert [row.tree_id for row in data["past_care"]] == [former.pk]

    def test_caring_trees_carry_the_last_watering_by_anyone(self, anna):
        tree = TreeFactory()
        assign(tree, anna)
        water(tree, UserFactory(), days_ago=3)
        latest = water(tree, anna, days_ago=1)

        [row] = user_trees(anna)["caring"]

        assert row.last_watered_at == latest.watered_at

    def test_archived_trees_stay_in_the_history(self, anna):
        """A yearly report covers what was removed — same rule as the CSV export."""
        tree = TreeFactory(created_by=anna, lifecycle=Tree.Lifecycle.ARCHIVED)

        assert [t.pk for t in user_trees(anna)["registered"]] == [tree.pk]

    def test_counts_waterings_and_activity(self, anna):
        tree = TreeFactory()
        water(tree, anna, days_ago=2)
        water(tree, anna, days_ago=40)
        ActivityEvent.objects.create(kind=ActivityEvent.Kind.LOGIN, user=anna)

        data = user_trees(anna)

        assert data["waterings_total"] == 2
        assert data["waterings_30"] == 1
        assert data["logins_30"] == 1

    def test_query_count_does_not_grow_with_trees(self, anna, django_assert_max_num_queries):
        for _ in range(10):
            tree = TreeFactory(created_by=anna)
            assign(tree, anna)
            water(tree, anna)

        with django_assert_max_num_queries(8):
            data = user_trees(anna)
            for tree in data["caring"] + data["registered"]:
                tree.locality.name  # noqa: B018 — touching the relation is the point


class TestUsersList:
    def test_shows_counts_per_person(self, client, admin, anna):
        TreeFactory(created_by=anna)
        TreeFactory(created_by=anna)
        assign(TreeFactory(), anna)

        response = client.get(reverse("panel:users"))

        row = next(p for p in response.context["users"] if p.pk == anna.pk)
        assert (row.trees_registered, row.trees_cared, row.waterings_30) == (2, 1, 0)
        page = response.content.decode()
        assert "Zarejestrowane" in page
        assert "Pod opieką" in page

    def test_counts_are_not_multiplied_by_each_other(self, client, admin, anna):
        """Three Counts over three joins multiply unless each is distinct."""
        trees = [TreeFactory(created_by=anna) for _ in range(3)]
        for tree in trees:
            assign(tree, anna)
            water(tree, anna)
            water(tree, anna)

        response = client.get(reverse("panel:users"))

        row = next(p for p in response.context["users"] if p.pk == anna.pk)
        assert (row.trees_registered, row.trees_cared, row.waterings_30) == (3, 3, 6)

    def test_ended_care_does_not_count(self, client, admin, anna):
        ended(TreeFactory(), anna, days_ago=1)

        response = client.get(reverse("panel:users"))

        row = next(p for p in response.context["users"] if p.pk == anna.pk)
        assert row.trees_cared == 0


class TestUserPage:
    def test_lists_trees_with_links_to_edit_them(self, client, admin, anna):
        registered = TreeFactory(created_by=anna, species="Lipa drobnolistna")
        cared = TreeFactory(species="Dąb szypułkowy")
        assign(cared, anna)

        page = client.get(reverse("panel:edit-user", kwargs={"user_id": anna.pk})).content.decode()

        assert "Pod opieką" in page
        assert "Zarejestrowane drzewa" in page
        assert "Dąb szypułkowy" in page
        assert "Lipa drobnolistna" in page
        assert reverse("panel:edit-tree", kwargs={"tree_id": cared.pk}) in page
        assert reverse("panel:edit-tree", kwargs={"tree_id": registered.pk}) in page

    def test_person_without_trees_gets_a_friendly_empty_state(self, client, admin, anna):
        page = client.get(reverse("panel:edit-user", kwargs={"user_id": anna.pk})).content.decode()

        assert "nie opiekuje się żadnym drzewem" in page

    def test_saving_the_form_still_works(self, client, admin, anna):
        response = client.post(
            reverse("panel:edit-user", kwargs={"user_id": anna.pk}),
            {"role": User.Role.VOLUNTEER, "is_active": "on"},
        )

        assert response.status_code == 302
