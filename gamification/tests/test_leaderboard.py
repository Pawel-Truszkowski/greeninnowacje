"""The 30-day ranking: who is in it, what counts, and where "me" ends up."""

from datetime import timedelta

import pytest
from django.utils import timezone

from accounts.models import User
from factories import TreeFactory, UserFactory
from gamification.rules import POINTS_PER_REGISTERED, POINTS_PER_TREE_DAY
from gamification.selectors import RANKING_DAYS, leaderboard, ranking_points
from trees.models import Tree
from trees.tests.factories import water

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    """Registers the test trees. An admin, so the registrations stay out of the ranking."""
    return UserFactory(role=User.Role.ADMIN)


@pytest.fixture
def trees(owner):
    return [TreeFactory(created_by=owner) for _ in range(12)]


def names(board):
    return [row.display_name for row in board["rows"]]


class TestWindow:
    def test_only_the_last_30_days_count(self, user, trees):
        water(trees[0], user, days_ago=RANKING_DAYS - 1)  # first day of the window
        water(trees[1], user, days_ago=RANKING_DAYS)  # the day before it

        assert ranking_points()[user.pk] == POINTS_PER_TREE_DAY

    def test_pressing_the_button_twice_is_one_tree_day(self, user, trees):
        water(trees[0], user)
        water(trees[0], user)

        assert ranking_points()[user.pk] == POINTS_PER_TREE_DAY

    def test_registrations_in_the_window_count(self, user):
        TreeFactory(created_by=user)
        old = TreeFactory(created_by=user)
        Tree.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=40))

        assert ranking_points()[user.pk] == POINTS_PER_REGISTERED


class TestWhoIsIn:
    def test_ordered_by_points(self, trees):
        busy, quiet = UserFactory(display_name="Basia"), UserFactory(display_name="Adam")
        water(trees[0], quiet)
        water(trees[0], busy)
        water(trees[1], busy)

        assert names(leaderboard()) == ["Basia", "Adam"]

    def test_ties_share_a_rank(self, trees):
        for name in ("Celina", "Bartek", "Ala"):
            water(trees[0], UserFactory(display_name=name))

        board = leaderboard()

        assert [row.rank for row in board["rows"]] == [1, 1, 1]
        assert names(board) == ["Ala", "Bartek", "Celina"]  # alphabetical within a tie

    def test_admins_and_inactive_accounts_are_left_out(self, trees):
        water(trees[0], UserFactory(role=User.Role.ADMIN, display_name="Admin"))
        water(trees[0], UserFactory(is_active=False, display_name="Uśpione"))
        water(trees[0], UserFactory(role=User.Role.COORDINATOR, display_name="Koordynatorka"))

        assert names(leaderboard()) == ["Koordynatorka"]

    def test_people_without_points_are_not_listed(self, user):
        assert leaderboard(me=user)["rows"] == []
        assert leaderboard(me=user)["ranked"] is False


class TestMe:
    def test_my_row_is_marked(self, user, trees):
        water(trees[0], user)

        [row] = leaderboard(me=user)["rows"]

        assert row.is_me
        assert leaderboard(me=user)["me"] is None  # already in the table

    def test_outside_the_top_i_still_see_my_place(self, user, trees):
        for index in range(10):
            person = UserFactory()
            water(trees[index], person)
            water(trees[index + 1], person)
        water(trees[0], user)

        board = leaderboard(me=user, size=10)

        assert len(board["rows"]) == 10
        assert board["me"].rank == 11
        assert board["me"].is_me


def test_query_count_does_not_grow_with_people(trees, django_assert_max_num_queries):
    for index in range(10):
        water(trees[index], UserFactory())

    with django_assert_max_num_queries(5):
        leaderboard()
