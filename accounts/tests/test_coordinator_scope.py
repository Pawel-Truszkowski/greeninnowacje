"""The coordinator's role and the reach of their area (Etap 2; architecture doc §3).

One assertion matters more than the rest: a coordinator is **not** an app admin. That single
property is what keeps the drought thresholds, the user accounts and the CSV exports with
volunteer names out of their hands, and nothing else in the codebase repeats the check.

The other half is `coordinator_localities()`. Every scoped query will be built on it, so if it
answers too generously once, it answers too generously everywhere.
"""

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.db.utils import IntegrityError
from django.http import HttpResponse
from django.test import RequestFactory

from accounts.models import CoordinatorArea, User
from accounts.permissions import (
    IsCoordinator,
    coordinator_localities,
    coordinator_required,
    is_coordinator,
)
from factories import LocalityFactory, UserFactory, oversee

pytestmark = pytest.mark.django_db


@pytest.fixture
def coordinator():
    return UserFactory(role=User.Role.COORDINATOR, display_name="Koordynator")


class TestRole:
    def test_coordinator_is_not_an_app_admin(self, coordinator):
        """The whole separation rests here — see the module docstring."""
        assert coordinator.is_app_admin is False

    def test_coordinator_is_recognised(self, coordinator):
        assert is_coordinator(coordinator) is True

    def test_admin_counts_as_a_coordinator(self):
        """Supervision includes the whole organisation, so the area screens open for admins."""
        assert is_coordinator(UserFactory(role=User.Role.ADMIN)) is True

    def test_volunteer_is_not(self):
        assert is_coordinator(UserFactory()) is False

    def test_anonymous_is_not(self):
        assert is_coordinator(AnonymousUser()) is False

    def test_role_label_is_polish(self):
        assert User.Role.COORDINATOR.label == "Koordynator"


class TestScope:
    def test_only_the_assigned_localities(self, coordinator):
        mine = LocalityFactory(name="Sierpc")
        LocalityFactory(name="Płock")  # somebody else's area
        oversee(coordinator, mine)

        names = set(coordinator_localities(coordinator).values_list("name", flat=True))

        assert names == {"Sierpc"}
        assert "Płock" not in names

    def test_several_localities_at_once(self, coordinator):
        for name in ("Sierpc", "Studzieniec"):
            oversee(coordinator, LocalityFactory(name=name))

        assert coordinator_localities(coordinator).count() == 2

    def test_admin_sees_every_locality(self):
        LocalityFactory(name="Sierpc")
        LocalityFactory(name="Płock")

        assert coordinator_localities(UserFactory(role=User.Role.ADMIN)).count() == 2

    def test_volunteer_has_no_scope(self):
        LocalityFactory()

        assert coordinator_localities(UserFactory()).count() == 0

    def test_anonymous_has_no_scope(self):
        LocalityFactory()

        assert coordinator_localities(AnonymousUser()).count() == 0

    def test_scope_is_a_queryset_not_a_list(self, coordinator):
        """Callers filter with `locality__in=scope`; a list would cost a second round trip."""
        oversee(coordinator, LocalityFactory())

        scope = coordinator_localities(coordinator)

        assert hasattr(scope, "filter"), "Zwróć QuerySet, nie listę"

    def test_coordinator_without_an_area_sees_nothing(self, coordinator):
        LocalityFactory()

        assert coordinator_localities(coordinator).count() == 0


class TestAreaModel:
    def test_the_same_locality_twice_is_refused(self, coordinator):
        locality = LocalityFactory()
        oversee(coordinator, locality)

        with pytest.raises(IntegrityError):
            oversee(coordinator, locality)

    def test_a_locality_may_have_a_second_coordinator(self, coordinator):
        """Holiday cover: the area is not owned by one person."""
        locality = LocalityFactory()
        oversee(coordinator, locality)

        oversee(UserFactory(role=User.Role.COORDINATOR), locality)

        assert locality.coordinators.count() == 2

    def test_table_name_and_polish_labels(self):
        meta = CoordinatorArea._meta

        assert meta.db_table == "coordinator_areas"
        assert meta.verbose_name == "obszar koordynatora"


class TestCoordinatorRequired:
    view = staticmethod(coordinator_required(lambda request: HttpResponse("ok")))

    def request_as(self, user):
        request = RequestFactory().get("/")
        request.user = user
        return request

    def test_anonymous_is_sent_to_login(self):
        assert self.view(self.request_as(AnonymousUser())).status_code == 302

    def test_volunteer_is_forbidden(self):
        with pytest.raises(PermissionDenied):
            self.view(self.request_as(UserFactory()))

    def test_coordinator_is_let_in(self, coordinator):
        assert self.view(self.request_as(coordinator)).status_code == 200

    def test_admin_is_let_in(self):
        assert self.view(self.request_as(UserFactory(role=User.Role.ADMIN))).status_code == 200


class TestDrfPermission:
    def request_as(self, user):
        request = RequestFactory().get("/")
        request.user = user
        return request

    @pytest.mark.parametrize(
        ("role", "allowed"),
        [(User.Role.VOLUNTEER, False), (User.Role.COORDINATOR, True), (User.Role.ADMIN, True)],
    )
    def test_who_passes(self, role, allowed):
        request = self.request_as(UserFactory(role=role))

        assert IsCoordinator().has_permission(request, None) is allowed

    def test_anonymous_does_not(self):
        request = self.request_as(AnonymousUser())

        assert IsCoordinator().has_permission(request, None) is False
