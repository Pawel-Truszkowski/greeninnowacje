import pytest
from django.contrib.auth import get_user
from django.test import Client
from django.urls import reverse

from accounts.models import User
from factories import TEST_PASSWORD, UserFactory

pytestmark = pytest.mark.django_db

LOGIN = reverse("accounts:login")
REGISTER = reverse("accounts:register")
LOGOUT = reverse("accounts:logout")
API_REGISTER = reverse("auth-api:api-register")
API_LOGIN = reverse("auth-api:api-login")
API_LOGOUT = reverse("auth-api:api-logout")

NEW_ACCOUNT = {"display_name": "Ola", "email": "Ola@Przyklad.pl", "password": "sadzimy-lipy-2026"}


class TestRegistrationPage:
    def test_creates_active_volunteer_and_logs_in(self, client):
        response = client.post(REGISTER, NEW_ACCOUNT)

        assert response.status_code == 302
        user = User.objects.get(email="ola@przyklad.pl")
        assert user.role == User.Role.VOLUNTEER and user.is_active
        assert get_user(client) == user

    @pytest.mark.parametrize(
        ("field", "value"),
        [("password", "za-krotk"), ("email", "nie-email"), ("display_name", "")],
    )
    def test_invalid_input_rerenders_form(self, client, field, value):
        response = client.post(REGISTER, NEW_ACCOUNT | {field: value})

        assert response.status_code == 200
        assert field in response.context["form"].errors
        assert not User.objects.exists()

    def test_duplicate_email_any_case(self, client):
        UserFactory(email="ola@przyklad.pl")
        response = client.post(REGISTER, NEW_ACCOUNT)
        assert "email" in response.context["form"].errors

    def test_role_cannot_be_injected(self, client):
        client.post(REGISTER, NEW_ACCOUNT | {"role": "admin", "is_staff": "on"})
        user = User.objects.get(email="ola@przyklad.pl")
        assert user.role == User.Role.VOLUNTEER and not user.is_staff


class TestLoginPage:
    def test_success_redirects_home(self, client, user):
        response = client.post(LOGIN, {"username": user.email, "password": TEST_PASSWORD})
        assert response.status_code == 302 and response.url == reverse("trees:map")
        assert get_user(client) == user

    def test_wrong_password(self, client, user):
        response = client.post(LOGIN, {"username": user.email, "password": "zle-haslo-123"})
        assert response.status_code == 200
        assert "Nieprawidłowy e-mail lub hasło." in response.content.decode()
        assert not get_user(client).is_authenticated

    @pytest.mark.parametrize(
        ("next_url", "expected"),
        [("/rejestracja", "/rejestracja"), ("https://evil.example/", "/"), ("//evil.example", "/")],
    )
    def test_next_only_to_same_site(self, client, user, next_url, expected):
        response = client.post(
            LOGIN, {"username": user.email, "password": TEST_PASSWORD, "next": next_url}
        )
        assert response.url == expected


class TestLogout:
    def test_get_not_allowed(self, client, user):
        client.force_login(user)
        assert client.get(LOGOUT).status_code == 405
        assert get_user(client).is_authenticated

    def test_post_logs_out(self, client, user):
        client.force_login(user)
        client.post(LOGOUT)
        assert not get_user(client).is_authenticated

    def test_deactivated_account_loses_session(self, client, user):
        client.force_login(user)
        User.objects.filter(pk=user.pk).update(is_active=False)
        assert not get_user(client).is_authenticated


class TestAuthApi:
    def test_register(self, client):
        response = client.post(API_REGISTER, NEW_ACCOUNT, content_type="application/json")

        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "ola@przyklad.pl" and body["role"] == "volunteer"
        assert "password" not in body
        assert get_user(client).is_authenticated

    def test_register_validation_errors(self, client):
        response = client.post(
            API_REGISTER, NEW_ACCOUNT | {"password": "krotkie"}, content_type="application/json"
        )
        assert response.status_code == 400
        assert "password" in response.json()["errors"]

    @pytest.mark.parametrize("body", ["{nie json", "[1, 2]"])
    def test_malformed_json(self, client, body):
        response = client.post(API_LOGIN, body, content_type="application/json")
        assert response.status_code == 400

    def test_login_and_logout(self, client, user):
        response = client.post(
            API_LOGIN,
            {"email": user.email.upper(), "password": TEST_PASSWORD},
            content_type="application/json",
        )
        assert response.status_code == 200 and response.json()["id"] == str(user.pk)

        assert client.post(API_LOGOUT).status_code == 204
        assert not get_user(client).is_authenticated

    def test_login_wrong_password(self, client, user):
        response = client.post(
            API_LOGIN, {"email": user.email, "password": "zle"}, content_type="application/json"
        )
        assert response.status_code == 400

    @pytest.mark.parametrize("method", ["get", "put", "delete"])
    def test_only_post(self, client, method):
        assert getattr(client, method)(API_LOGIN).status_code == 405


class TestCsrf:
    """Login CSRF: auth endpoints must reject cross-site posts even for anonymous users."""

    @pytest.mark.parametrize("url", [LOGIN, REGISTER, API_LOGIN, API_REGISTER])
    def test_post_without_token_rejected(self, user, url):
        csrf_client = Client(enforce_csrf_checks=True)
        response = csrf_client.post(
            url, {"email": user.email, "password": TEST_PASSWORD}, content_type="application/json"
        )
        assert response.status_code == 403

    def test_api_login_with_token(self, user):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.get(reverse("trees:map"))  # sets the csrftoken cookie
        token = csrf_client.cookies["csrftoken"].value
        response = csrf_client.post(
            API_LOGIN,
            {"email": user.email, "password": TEST_PASSWORD},
            content_type="application/json",
            headers={"X-CSRFToken": token},
        )
        assert response.status_code == 200


class TestRateLimit:
    """Spec §7: login and registration limited to 10 attempts / 15 min / IP."""

    def _attempt(self, client, **extra):
        return client.post(
            API_LOGIN, {"email": "x@przyklad.pl", "password": "zle"},
            content_type="application/json", **extra,
        )  # fmt: skip

    def test_eleventh_login_attempt_blocked(self, client):
        statuses = [self._attempt(client).status_code for _ in range(11)]
        assert statuses[:10] == [400] * 10
        assert statuses[10] == 429

    def test_limit_shared_between_page_and_api(self, client):
        for _ in range(10):
            self._attempt(client)
        response = client.post(LOGIN, {"username": "x@przyklad.pl", "password": "zle"})
        assert response.status_code == 429

    def test_blocked_even_with_correct_password(self, client, user):
        for _ in range(10):
            self._attempt(client)
        response = client.post(
            API_LOGIN, {"email": user.email, "password": TEST_PASSWORD},
            content_type="application/json",
        )  # fmt: skip
        assert response.status_code == 429
        assert not get_user(client).is_authenticated

    def test_other_ip_unaffected(self, client):
        for _ in range(11):
            self._attempt(client)
        assert self._attempt(client, REMOTE_ADDR="10.0.0.2").status_code == 400

    def test_spoofed_forwarded_for_ignored_without_trusted_proxy(self, client):
        for _ in range(10):
            self._attempt(client)
        response = self._attempt(client, HTTP_X_FORWARDED_FOR="203.0.113.7")
        assert response.status_code == 429

    def test_behind_trusted_proxy_uses_forwarded_client(self, client, settings):
        settings.TRUSTED_PROXY_HOPS = 1
        for _ in range(10):
            self._attempt(client, HTTP_X_FORWARDED_FOR="203.0.113.7")
        # Same proxy, different real client → separate bucket; a client-prepended fake
        # entry doesn't matter because only the proxy-appended (rightmost) one counts.
        assert self._attempt(client, HTTP_X_FORWARDED_FOR="203.0.113.8").status_code == 400
        blocked = self._attempt(client, HTTP_X_FORWARDED_FOR="1.2.3.4, 203.0.113.7")
        assert blocked.status_code == 429

    def test_registration_limited(self):
        # A fresh client per attempt: a successful sign-up logs the client in, and
        # logged-in users are redirected away from the form. Same IP for all of them.
        statuses = [
            Client().post(REGISTER, NEW_ACCOUNT | {"email": f"u{i}@przyklad.pl"}).status_code
            for i in range(11)
        ]
        assert statuses[:10] == [302] * 10 and statuses[10] == 429
