"""JSON auth endpoints (spec §4): /api/auth/register, /api/auth/login, /api/auth/logout,
/api/auth/password-reset and /api/auth/password-reset/confirm.

Plain Django views rather than DRF on purpose: DRF only enforces CSRF for already
authenticated sessions, whereas login/registration need it too (login CSRF). Django's
CsrfViewMiddleware checks these views; clients send the csrftoken cookie value in the
X-CSRFToken header.
"""

import json

from django.contrib.auth import login, logout
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST

from core.ratelimit import rate_limit

from . import services
from .forms import LoginForm, NewPasswordForm, PasswordResetRequestForm, RegistrationForm
from .views import RATE_LIMITED_MESSAGE, auth_rate


def user_payload(user):
    return {
        "id": str(user.pk),
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
    }


def _json_body(request):
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _errors(form):
    return JsonResponse({"errors": form.errors.get_json_data()}, status=400)


def _limited():
    return JsonResponse({"detail": RATE_LIMITED_MESSAGE}, status=429)


def _bad_json():
    return JsonResponse({"detail": "Nieprawidłowe dane (oczekiwano JSON)."}, status=400)


@require_POST
@rate_limit("auth-register", auth_rate)
def register(request):
    if request.limited:
        return _limited()
    data = _json_body(request)
    if data is None:
        return _bad_json()
    form = RegistrationForm(data)
    if not form.is_valid():
        return _errors(form)
    user = form.save()
    login(request, user)
    return JsonResponse(user_payload(user), status=201)


@require_POST
@rate_limit("auth-login", auth_rate)
def login_api(request):
    if request.limited:
        return _limited()
    data = _json_body(request)
    if data is None:
        return _bad_json()
    form = LoginForm(
        request, data={"username": data.get("email"), "password": data.get("password")}
    )
    if not form.is_valid():
        return _errors(form)
    login(request, form.get_user())
    return JsonResponse(user_payload(form.get_user()))


@require_POST
def logout_api(request):
    logout(request)
    return HttpResponse(status=204)


RESET_SENT_MESSAGE = "Jeśli konto z tym adresem istnieje, wysłaliśmy link do ustawienia hasła."
RESET_LINK_INVALID_MESSAGE = "Link wygasł lub został już użyty. Poproś o nowy."


@require_POST
@rate_limit("auth-password-reset", auth_rate)
def password_reset(request):
    if request.limited:
        return _limited()
    data = _json_body(request)
    if data is None:
        return _bad_json()
    form = PasswordResetRequestForm(data)
    if not form.is_valid():
        return _errors(form)
    services.request_password_reset(form.cleaned_data["email"])
    # 202 whatever happened — the response must not reveal whether the account exists.
    return JsonResponse({"detail": RESET_SENT_MESSAGE}, status=202)


@require_POST
@rate_limit("auth-password-reset", auth_rate)
def password_reset_confirm(request):
    """Sets the new password; does not log in (the client can call /api/auth/login)."""
    if request.limited:
        return _limited()
    data = _json_body(request)
    if data is None:
        return _bad_json()
    user = services.user_from_reset_link(str(data.get("uid", "")), str(data.get("token", "")))
    if user is None:
        return JsonResponse({"detail": RESET_LINK_INVALID_MESSAGE}, status=400)
    form = NewPasswordForm(user, data)
    if not form.is_valid():
        return _errors(form)
    form.save()
    return HttpResponse(status=204)
