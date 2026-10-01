"""A coordinator managing somebody else's assignment (architecture doc §3).

This is the first place in the codebase where one person commits another, so the area check
carries real weight: without it the role is not „nadzór nad obszarem" but over the whole map.
Every test here puts a second locality in the database for that reason.

The checks live in the service, not the view, for the same reason every other invariant does —
the page and the API must not be able to disagree about who may do what.
"""

import pytest

from accounts.models import User
from factories import LocalityFactory, TreeFactory, UserFactory, oversee
from trees.models import Assignment, Tree
from trees.services import (
    CaretakerConflict,
    OutsideArea,
    assign_caretaker_for,
    caretaker_of,
    release_caretaker_of,
)
from trees.tests.factories import assign

pytestmark = pytest.mark.django_db


@pytest.fixture
def area():
    coordinator = UserFactory(role=User.Role.COORDINATOR)
    mine, theirs = LocalityFactory(name="Sierpc"), LocalityFactory(name="Płock")
    oversee(coordinator, mine)
    return coordinator, mine, theirs


class TestAssigning:
    def test_puts_a_volunteer_in_charge(self, area):
        coordinator, mine, _ = area
        tree, volunteer = TreeFactory(locality=mine), UserFactory(display_name="Anna")

        assign_caretaker_for(tree, volunteer, by=coordinator)

        assert caretaker_of(tree) == volunteer

    def test_refuses_a_tree_outside_the_area(self, area):
        """The whole point of the role having a scope."""
        coordinator, _, theirs = area
        tree = TreeFactory(locality=theirs)

        with pytest.raises(OutsideArea):
            assign_caretaker_for(tree, UserFactory(), by=coordinator)

        assert caretaker_of(tree) is None

    def test_a_tree_that_already_has_somebody_is_a_conflict(self, area):
        """Taking a tree from a volunteer should be a decision, not a side effect."""
        coordinator, mine, _ = area
        tree = TreeFactory(locality=mine)
        assign(tree, UserFactory(display_name="Pierwsza"))

        with pytest.raises(CaretakerConflict):
            assign_caretaker_for(tree, UserFactory(), by=coordinator)

        assert caretaker_of(tree).display_name == "Pierwsza"

    def test_admin_may_assign_anywhere(self, area):
        _, _, theirs = area
        tree = TreeFactory(locality=theirs)
        volunteer = UserFactory()

        assign_caretaker_for(tree, volunteer, by=UserFactory(role=User.Role.ADMIN))

        assert caretaker_of(tree) == volunteer

    def test_a_volunteer_cannot_commit_somebody_else(self, area):
        """`assign_caretaker` is for taking a tree yourself; this is not that."""
        _, mine, _ = area
        tree = TreeFactory(locality=mine)

        with pytest.raises(OutsideArea):
            assign_caretaker_for(tree, UserFactory(), by=UserFactory())

    def test_archived_trees_are_refused(self, area):
        coordinator, mine, _ = area
        tree = TreeFactory(locality=mine, lifecycle=Tree.Lifecycle.ARCHIVED)

        with pytest.raises((OutsideArea, CaretakerConflict, ValueError)):
            assign_caretaker_for(tree, UserFactory(), by=coordinator)

    def test_an_inactive_volunteer_is_refused(self, area):
        """A blocked account would get e-mails it can no longer act on."""
        coordinator, mine, _ = area
        tree = TreeFactory(locality=mine)

        with pytest.raises(ValueError):
            assign_caretaker_for(tree, UserFactory(is_active=False), by=coordinator)


class TestReleasing:
    def test_ends_somebody_elses_assignment(self, area):
        coordinator, mine, _ = area
        tree = TreeFactory(locality=mine)
        assign(tree, UserFactory())

        assert release_caretaker_of(tree, by=coordinator) is True
        assert caretaker_of(tree) is None

    def test_history_survives(self, area):
        """Spec §3: who looked after what is never deleted, only ended."""
        coordinator, mine, _ = area
        tree = TreeFactory(locality=mine)
        volunteer = UserFactory()
        assign(tree, volunteer)

        release_caretaker_of(tree, by=coordinator)

        past = Assignment.objects.get(tree=tree, user=volunteer)
        assert past.ended_at is not None

    def test_refuses_a_tree_outside_the_area(self, area):
        coordinator, _, theirs = area
        tree = TreeFactory(locality=theirs)
        assign(tree, UserFactory())

        with pytest.raises(OutsideArea):
            release_caretaker_of(tree, by=coordinator)

        assert caretaker_of(tree) is not None

    def test_nothing_to_release_is_false_not_an_error(self, area):
        coordinator, mine, _ = area

        assert release_caretaker_of(TreeFactory(locality=mine), by=coordinator) is False

    def test_a_released_tree_can_be_assigned_again(self, area):
        """Reassigning is two steps, and the second one has to work."""
        coordinator, mine, _ = area
        tree = TreeFactory(locality=mine)
        assign(tree, UserFactory(display_name="Pierwsza"))
        release_caretaker_of(tree, by=coordinator)

        assign_caretaker_for(tree, UserFactory(display_name="Druga"), by=coordinator)

        assert caretaker_of(tree).display_name == "Druga"

    def test_volunteer_cannot_release_somebody_else(self, area):
        _, mine, _ = area
        tree = TreeFactory(locality=mine)
        assign(tree, UserFactory())

        with pytest.raises(OutsideArea):
            release_caretaker_of(tree, by=UserFactory())


class TestMessages:
    def test_outside_area_explains_itself_in_polish(self, area):
        coordinator, _, theirs = area

        with pytest.raises(OutsideArea) as error:
            assign_caretaker_for(TreeFactory(locality=theirs), UserFactory(), by=coordinator)

        message = str(error.value)
        assert message and message[0].isupper()
        assert "Traceback" not in message


def test_release_touches_only_the_named_tree(area):
    """A sanity check on the filter: one call, one tree."""
    coordinator, mine, _ = area
    kept, released = TreeFactory(locality=mine), TreeFactory(locality=mine)
    assign(kept, UserFactory())
    assign(released, UserFactory())

    release_caretaker_of(released, by=coordinator)

    assert caretaker_of(kept) is not None
    assert Assignment.objects.filter(tree=kept, ended_at__isnull=True).count() == 1
