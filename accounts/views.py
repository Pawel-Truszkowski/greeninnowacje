from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core.ratelimit import rate_limit

from .forms import LoginForm, RegistrationForm

RATE_LIMITED_MESSAGE = "Za dużo prób. Odczekaj kilkanaście minut i spróbuj ponownie."


def auth_rate():
    return settings.AUTH_RATE_LIMIT


def safe_next(request):
    """Post-login redirect target from ?next=, only if it points back at this site."""
    target = request.POST.get("next") or request.GET.get("next")
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return settings.LOGIN_REDIRECT_URL


@rate_limit("auth-login", auth_rate)
def login_view(request):
    if request.user.is_authenticated:
        return redirect(safe_next(request))
    form = LoginForm(request, data=request.POST or None)
    status = 200
    if request.method == "POST":
        if request.limited:
            form.add_error(None, RATE_LIMITED_MESSAGE)
            status = 429
        elif form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f"Witaj z powrotem, {user.display_name}! 🌱")
            return redirect(safe_next(request))
    context = {"form": form, "next": safe_next(request)}
    return render(request, "accounts/login.html", context, status=status)


@rate_limit("auth-register", auth_rate)
def register_view(request):
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)
    form = RegistrationForm(request.POST or None)
    status = 200
    if request.method == "POST":
        if request.limited:
            form.add_error(None, RATE_LIMITED_MESSAGE)
            status = 429
        elif form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "🎉 Witamy w GREENowacjach! Konto założone.")
            return redirect(settings.LOGIN_REDIRECT_URL)
    return render(request, "accounts/register.html", {"form": form}, status=status)


@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, "Wylogowano. Do zobaczenia przy drzewach! 👋")
    return redirect(settings.LOGIN_REDIRECT_URL)
