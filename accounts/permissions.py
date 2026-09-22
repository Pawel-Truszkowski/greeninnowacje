"""Role checks shared by DRF endpoints and Django views (spec §4: enforced server-side).

Volunteer endpoints are open to every logged-in user (admins can do everything a volunteer
can). Inactive accounts never get this far: the auth backend refuses to load them, which
also ends their existing sessions.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission


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
