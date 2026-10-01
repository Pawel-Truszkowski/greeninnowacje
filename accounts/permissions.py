"""Role checks shared by DRF endpoints and Django views (spec §4: enforced server-side).

Volunteer endpoints are open to every logged-in user (admins can do everything a volunteer
can). Inactive accounts never get this far: the auth backend refuses to load them, which
also ends their existing sessions.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

from trees.models import Locality

from .models import User


def is_app_admin(user):
    return user.is_authenticated and user.is_app_admin


class IsVolunteer(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated


class IsAppAdmin(BasePermission):
    def has_permission(self, request, view):
        return is_app_admin(request.user)


def app_admin_required(view):
    """Anonymous → login page; logged-in non-admin → 403."""

    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not is_app_admin(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


# --- coordinator (Etap 2; architecture doc §3) ----------------------------------------


def is_coordinator(user):
    """Whether `user` oversees an area. An admin oversees everything, so counts as one.

    Note what this is *not*: a coordinator is not an app admin. `is_app_admin` stays false
    for them, which is what keeps the drought thresholds, the user accounts and the CSV
    exports out of their reach.
    """
    return user.is_authenticated and (user.is_app_admin or user.role == User.Role.COORDINATOR)


def coordinator_localities(user):
    """The localities this user may look at, as a `QuerySet[Locality]`.

    Every scoped query goes through this, so it is the single place that decides what "my
    area" means:
      coordinator → the localities in their `CoordinatorArea` rows
      admin       → all of them; supervision includes the whole organisation
      anyone else → none, including anonymous users

    A queryset rather than a list: callers filter trees with `locality__in=…` and a list
    would turn that into a second round trip.
    """
    if not user.is_authenticated:
        return Locality.objects.none()
    if user.is_app_admin:
        return Locality.objects.all()
    return Locality.objects.filter(coordinators__user=user)


class IsCoordinator(BasePermission):
    """DRF: the area screens. Admins pass too — they supervise coordinators."""

    def has_permission(self, request, view):
        return is_coordinator(request.user)


def coordinator_required(view):
    """Anonymous → login page; logged-in non-coordinator → 403 (as `app_admin_required`)."""

    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not is_coordinator(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper
