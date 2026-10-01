"""Granting the coordinator role and its area from the admin panel (Etap 2).

The role is only half of it: a coordinator without localities oversees nothing, so the two
are set together on one screen. Anything else means an admin can create a role that silently
does not work.
"""

import pytest
from django.urls import reverse

from accounts.models import CoordinatorArea, User
from factories import LocalityFactory, UserFactory, oversee
from panel.forms import UserAdminForm

pytestmark = pytest.mark.django_db


@pytest.fixture
def as_admin(client):
    client.force_login(UserFactory(role=User.Role.ADMIN))
    return client


class TestForm:
    def test_coordinator_is_offered_as_a_role(self):
        choices = dict(UserAdminForm().fields["role"].choices)

        assert User.Role.COORDINATOR in choices
        assert choices[User.Role.COORDINATOR] == "Koordynator"

    def test_localities_can_be_chosen(self):
        """Without this the role is a label with no reach."""
        assert "localities" in UserAdminForm().fields

    def test_saving_sets_the_area(self):
        volunteer = UserFactory()
        locality = LocalityFactory(name="Sierpc")

        form = UserAdminForm(
            {"role": User.Role.COORDINATOR, "is_active": True, "localities": [locality.pk]},
            instance=volunteer,
        )
        assert form.is_valid(), form.errors
        form.save()

        assert list(volunteer.areas.values_list("locality__name", flat=True)) == ["Sierpc"]

    def test_removing_a_locality_removes_the_area(self):
        coordinator = UserFactory(role=User.Role.COORDINATOR)
        kept, dropped = LocalityFactory(name="Sierpc"), LocalityFactory(name="Płock")
        oversee(coordinator, kept)
        oversee(coordinator, dropped)

        form = UserAdminForm(
            {"role": User.Role.COORDINATOR, "is_active": True, "localities": [kept.pk]},
            instance=coordinator,
        )
        assert form.is_valid(), form.errors
        form.save()

        assert list(coordinator.areas.values_list("locality__name", flat=True)) == ["Sierpc"]

    def test_demoting_a_coordinator_clears_their_area(self):
        """A volunteer with leftover area rows would be a coordinator in all but name."""
        coordinator = UserFactory(role=User.Role.COORDINATOR)
        oversee(coordinator, LocalityFactory())

        form = UserAdminForm(
            {"role": User.Role.VOLUNTEER, "is_active": True, "localities": []},
            instance=coordinator,
        )
        assert form.is_valid(), form.errors
        form.save()

        assert not CoordinatorArea.objects.filter(user=coordinator).exists()

    def test_admin_still_cannot_demote_themselves(self):
        """The existing guard must survive the new field."""
        admin = UserFactory(role=User.Role.ADMIN)

        form = UserAdminForm(
            {"role": User.Role.COORDINATOR, "is_active": True, "localities": []},
            instance=admin,
            editor=admin,
        )

        assert not form.is_valid()


class TestPage:
    def test_edit_screen_offers_the_localities(self, as_admin):
        volunteer = UserFactory()
        LocalityFactory(name="Studzieniec")

        content = as_admin.get(
            reverse("panel:edit-user", kwargs={"user_id": volunteer.pk})
        ).content.decode()

        assert "Studzieniec" in content
        assert "Koordynator" in content

    def test_user_list_shows_the_role(self, as_admin):
        UserFactory(role=User.Role.COORDINATOR, display_name="Ktoś")

        content = as_admin.get(reverse("panel:users")).content.decode()

        assert "Koordynator" in content
