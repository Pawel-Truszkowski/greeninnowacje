"""JSON auth endpoints (spec §4): /api/auth/register, /api/auth/login, /api/auth/logout.

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

from .forms import LoginForm, RegistrationForm
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
