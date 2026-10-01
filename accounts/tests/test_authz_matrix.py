"""Endpoint × role authorization matrix (spec §7, §9).

Every endpoint gets a row. When you add an endpoint, add it here with the expected status
for each role — a missing row is a missing authorization test.
"""

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import reverse

from accounts.permissions import IsAppAdmin, IsVolunteer, app_admin_required
from factories import UserFactory

pytestmark = pytest.mark.django_db

ROLES = ("anonymous", "volunteer", "coordinator", "admin")

# (method, url name, url kwargs, {role: expected status})
ENDPOINTS = [
    (
        "get",
        "trees:map",
        {},
        {"anonymous": 200, "volunteer": 200, "coordinator": 200, "admin": 200},
    ),
    (
        "get",
        "accounts:login",
        {},
        {"anonymous": 200, "volunteer": 302, "coordinator": 302, "admin": 302},
    ),
    (
        "get",
        "accounts:register",
        {},
        {"anonymous": 200, "volunteer": 302, "coordinator": 302, "admin": 302},
    ),
    (
        "post",
        "accounts:logout",
        {},
        {"anonymous": 302, "volunteer": 302, "coordinator": 302, "admin": 302},
    ),
    (
        "post",
        "auth-api:api-logout",
        {},
        {"anonymous": 204, "volunteer": 204, "coordinator": 204, "admin": 204},
    ),
    (
        "get",
        "trees-api:list",
        {},
        {"anonymous": 200, "volunteer": 200, "coordinator": 200, "admin": 200},
    ),
    (
        "get",
        "me-api:trees",
        {},
        {"anonymous": 403, "volunteer": 200, "coordinator": 200, "admin": 200},
    ),
    # 400: no coordinates — the point is that anonymous users never reach the geocoder.
    (
        "get",
        "trees-api:locality-hint",
        {},
        {"anonymous": 403, "volunteer": 400, "coordinator": 400, "admin": 400},
    ),
    ("get", "trees:my", {}, {"anonymous": 302, "volunteer": 200, "coordinator": 200, "admin": 200}),
    (
        "get",
        "trees:register",
        {},
        {"anonymous": 302, "volunteer": 200, "coordinator": 200, "admin": 200},
    ),
    # 400: empty payload — the point is that anonymous users never get that far.
    (
        "post",
        "trees-api:create",
        {},
        {"anonymous": 403, "volunteer": 400, "coordinator": 400, "admin": 400},
    ),
    # Admin panel (spec §4): volunteers are forbidden, guests are sent to the login page.
    (
        "get",
        "panel:dashboard",
        {},
        {"anonymous": 302, "volunteer": 403, "coordinator": 403, "admin": 200},
    ),
    (
        "get",
        "panel:thresholds",
        {},
        {"anonymous": 302, "volunteer": 403, "coordinator": 403, "admin": 200},
    ),
    (
        "get",
        "panel:users",
        {},
        {"anonymous": 302, "volunteer": 403, "coordinator": 403, "admin": 200},
    ),
    (
        "get",
        "panel:trees",
        {},
        {"anonymous": 302, "volunteer": 403, "coordinator": 403, "admin": 200},
    ),
    (
        "post",
        "panel:recompute",
        {},
        {"anonymous": 302, "volunteer": 403, "coordinator": 403, "admin": 302},
    ),
    (
        "get",
        "admin-api:stats",
        {},
        {"anonymous": 403, "volunteer": 403, "coordinator": 403, "admin": 200},
    ),
    (
        "get",
        "admin-api:config",
        {},
        {"anonymous": 403, "volunteer": 403, "coordinator": 403, "admin": 200},
    ),
    (
        "get",
        "admin-api:users",
        {},
        {"anonymous": 403, "volunteer": 403, "coordinator": 403, "admin": 200},
    ),
    # CSV exports (spec §4): rows carry volunteer names, so admin only.
    (
        "get",
        "admin-api:export-trees",
        {},
        {"anonymous": 403, "volunteer": 403, "coordinator": 403, "admin": 200},
    ),
    (
        "get",
        "admin-api:export-waterings",
        {},
        {"anonymous": 403, "volunteer": 403, "coordinator": 403, "admin": 200},
    ),
    (
        "get",
        "admin-api:export-weather",
        {},
        {"anonymous": 403, "volunteer": 403, "coordinator": 403, "admin": 200},
    ),
    (
        "get",
        "panel:export",
        {},
        {"anonymous": 302, "volunteer": 403, "coordinator": 403, "admin": 200},
    ),
    (
        "get",
        "panel:photos",
        {},
        {"anonymous": 302, "volunteer": 403, "coordinator": 403, "admin": 200},
    ),
    # The area screens: a coordinator's own ground, an admin supervises, nobody else.
    (
        "get",
        "coordinator:overview",
        {},
        {"anonymous": 302, "volunteer": 403, "coordinator": 200, "admin": 200},
    ),
]

# Same, for endpoints that need an existing tree (kwargs built per test).
TREE_ENDPOINTS = [
    ("get", "trees:card", {"anonymous": 200, "volunteer": 200, "coordinator": 200, "admin": 200}),
    (
        "get",
        "trees-api:public",
        {"anonymous": 200, "volunteer": 200, "coordinator": 200, "admin": 200},
    ),
    ("get", "trees-api:qr", {"anonymous": 200, "volunteer": 200, "coordinator": 200, "admin": 200}),
    (
        "get",
        "trees-api:detail",
        {"anonymous": 403, "volunteer": 200, "coordinator": 200, "admin": 200},
    ),
    (
        "post",
        "trees-api:waterings",
        {"anonymous": 403, "volunteer": 201, "coordinator": 201, "admin": 201},
    ),
    (
        "post",
        "trees-api:assign",
        {"anonymous": 403, "volunteer": 201, "coordinator": 201, "admin": 201},
    ),
    # 400: nothing to release — the point is that anonymous users are stopped earlier.
    (
        "post",
        "trees-api:unassign",
        {"anonymous": 403, "volunteer": 400, "coordinator": 400, "admin": 400},
    ),
    # Photos (Etap 2) are narrower than watering: the tree here belongs to somebody else, so a
    # plain volunteer is refused outright, while the admin gets 400 for sending no file.
    (
        "post",
        "trees-api:photos",
        {"anonymous": 403, "volunteer": 403, "coordinator": 403, "admin": 400},
    ),
    # Pages redirect: anonymous to the login form, logged-in users back to the card.
    ("post", "trees:water", {"anonymous": 302, "volunteer": 302, "coordinator": 302, "admin": 302}),
    (
        "post",
        "trees:add-photo",
        {"anonymous": 302, "volunteer": 302, "coordinator": 302, "admin": 302},
    ),
    (
        "post",
        "trees:take-care",
        {"anonymous": 302, "volunteer": 302, "coordinator": 302, "admin": 302},
    ),
    (
        "post",
        "trees:stop-care",
        {"anonymous": 302, "volunteer": 302, "coordinator": 302, "admin": 302},
    ),
]


@pytest.fixture
def client_as(client):
    def make(role):
        if role != "anonymous":
            client.force_login(UserFactory(role=role))
        return client

    return make


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize(
    ("method", "name", "kwargs", "expected"),
    ENDPOINTS,
    ids=[f"{m.upper()} {n}" for m, n, *_ in ENDPOINTS],
)
def test_endpoint_access(client_as, role, method, name, kwargs, expected):
    response = getattr(client_as(role), method)(reverse(name, kwargs=kwargs))
    assert response.status_code == expected[role]


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize(
    ("method", "name", "expected"),
    TREE_ENDPOINTS,
    ids=[f"{m.upper()} {n}" for m, n, *_ in TREE_ENDPOINTS],
)
def test_tree_endpoint_access(client_as, tree, role, method, name, expected):
    url = reverse(name, kwargs={"tree_id": tree.pk})
    assert getattr(client_as(role), method)(url).status_code == expected[role]


@pytest.fixture
def request_as(rf: RequestFactory):
    def make(role):
        request = rf.get("/")
        request.user = (
            AnonymousUser()
            if role == "anonymous"
            else UserFactory(role="admin" if role == "admin" else "volunteer")
        )
        return request

    return make


@pytest.mark.parametrize(
    ("role", "volunteer_ok", "admin_ok"),
    [("anonymous", False, False), ("volunteer", True, False), ("admin", True, True)],
)
def test_drf_permission_classes(request_as, role, volunteer_ok, admin_ok):
    request = request_as(role)
    assert IsVolunteer().has_permission(request, None) is volunteer_ok
    assert IsAppAdmin().has_permission(request, None) is admin_ok


class TestAppAdminRequired:
    view = staticmethod(app_admin_required(lambda request: HttpResponse("ok")))

    def test_anonymous_redirected_to_login(self, request_as):
        response = self.view(request_as("anonymous"))
        assert response.status_code == 302
        assert response.url.startswith(reverse("accounts:login"))

    def test_volunteer_forbidden(self, request_as):
        with pytest.raises(PermissionDenied):
            self.view(request_as("volunteer"))

    def test_admin_allowed(self, request_as):
        assert self.view(request_as("admin")).status_code == 200
