"""Map for a logged-in volunteer (UI doc §8.2): "my" trees and the register button.

These tests are the specification for the `is_mine` flag: they were written before the
implementation and describe what the endpoint and the page must do.
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from factories import TreeFactory, UserFactory
from trees.tests.factories import assign

pytestmark = pytest.mark.django_db

LIST_URL = reverse("trees-api:list")
MAP_URL = reverse("trees:map")
REGISTER_LABEL = "Zarejestruj drzewo tutaj"


@pytest.fixture
def volunteer(client):
    user = UserFactory()
    client.force_login(user)
    return user


def payload_by_id(response):
    return {tree["id"]: tree for tree in response.json()}


class TestIsMineFlag:
    def test_anonymous_sees_no_tree_as_theirs(self, client):
        tree = TreeFactory()
        assign(tree, UserFactory())

        (payload,) = client.get(LIST_URL).json()

        assert payload["is_mine"] is False

    def test_my_tree_is_marked(self, client, volunteer):
        mine = TreeFactory()
        assign(mine, volunteer)

        (payload,) = client.get(LIST_URL).json()

        assert payload["is_mine"] is True

    def test_somebody_elses_tree_is_not(self, client, volunteer):
        theirs = TreeFactory()
        assign(theirs, UserFactory())

        (payload,) = client.get(LIST_URL).json()

        assert payload["is_mine"] is False
        # The flag says "mine", never who the caretaker is.
        assert payload["has_caretaker"] is True

    def test_tree_without_caretaker_is_not_mine(self, client, volunteer):
        TreeFactory()

        (payload,) = client.get(LIST_URL).json()

        assert payload["is_mine"] is False

    def test_finished_care_does_not_count(self, client, volunteer):
        tree = TreeFactory()
        assignment = assign(tree, volunteer)
        assignment.ended_at = timezone.now()
        assignment.save()

        (payload,) = client.get(LIST_URL).json()

        assert payload["is_mine"] is False

    def test_mixed_list(self, client, volunteer):
        mine = TreeFactory()
        theirs = TreeFactory()
        free = TreeFactory()
        assign(mine, volunteer)
        assign(theirs, UserFactory())

        payloads = payload_by_id(client.get(LIST_URL))

        assert payloads[str(mine.pk)]["is_mine"] is True
        assert payloads[str(theirs.pk)]["is_mine"] is False
        assert payloads[str(free.pk)]["is_mine"] is False

    def test_filters_still_work_together_with_the_flag(self, client, volunteer):
        mine = TreeFactory(status="URGENT")
        assign(mine, volunteer)
        TreeFactory(status="OK")

        body = client.get(LIST_URL, {"status": "URGENT"}).json()

        assert [tree["id"] for tree in body] == [str(mine.pk)]
        assert body[0]["is_mine"] is True


class TestSharedPayload:
    def test_my_trees_endpoint_still_works(self, client, volunteer):
        """`map_tree_payload` is shared with /api/me/trees, which has no such annotation."""
        tree = TreeFactory()
        assign(tree, volunteer)

        response = client.get(reverse("me-api:trees"))

        assert response.status_code == 200
        assert response.json()[0]["id"] == str(tree.pk)


class TestQueryCount:
    def test_flag_does_not_add_a_query_per_tree(self, client, volunteer, django_assert_num_queries):
        for _ in range(3):
            assign(TreeFactory(), volunteer)
        with CaptureQueriesContext(connection) as captured:
            client.get(LIST_URL)
        baseline = len(captured.captured_queries)

        for _ in range(7):
            assign(TreeFactory(), volunteer)
        with django_assert_num_queries(baseline):
            client.get(LIST_URL)


class TestMapPage:
    def test_logged_in_volunteer_sees_the_register_button(self, client, volunteer):
        content = client.get(MAP_URL).content.decode()

        assert REGISTER_LABEL in content
        assert reverse("trees:register") in content

    def test_guest_does_not(self, client):
        assert REGISTER_LABEL not in client.get(MAP_URL).content.decode()
