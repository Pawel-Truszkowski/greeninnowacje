import re
from datetime import timedelta

import pytest
from django.contrib.auth import get_user
from django.contrib.auth.tokens import default_token_generator
from django.test import Client
from django.urls import reverse

from accounts import services
from factories import TEST_PASSWORD, UserFactory
from notifications.models import EmailLog

pytestmark = pytest.mark.django_db

RESET = reverse("accounts:password-reset")
SENT = reverse("accounts:password-reset-sent")
API_RESET = reverse("auth-api:api-password-reset")
API_CONFIRM = reverse("auth-api:api-password-reset-confirm")
NEW_PASSWORD = "nowe-lipy-w-parku-2026"


@pytest.fixture(autouse=True)
def base_url(settings):
    settings.APP_BASE_URL = "https://greenowacje.example"


def link_from(mail):
    (url,) = set(re.findall(r"https://greenowacje\.example/\S+", mail.body))
    return url.removeprefix("https://greenowacje.example")


def uid_and_token(path):
    *_, uid, token = path.rstrip("/").split("/")
    return uid, token


def request_link(client, email):
    return client.post(RESET, {"email": email})


class TestRequestPage:
    def test_sends_link_built_from_app_base_url(self, client, user, mailoutbox, settings):
        # ALLOWED_HOSTS normally rejects a foreign Host; the link must not depend on it.
        settings.ALLOWED_HOSTS = ["*"]
        response = client.post(RESET, {"email": user.email}, HTTP_HOST="evil.example")

        assert response.status_code == 302 and response.url == SENT
        (mail,) = mailoutbox
        assert mail.to == [user.email]
        assert "evil.example" not in mail.body
        assert link_from(mail).startswith("/ustaw-haslo/")
        assert "https://greenowacje.example/ustaw-haslo/" in mail.alternatives[0][0]

    def test_email_is_case_insensitive(self, client, mailoutbox):
        user = UserFactory(email="ala@przyklad.pl")
        request_link(client, "  Ala@Przyklad.PL ")
        assert [m.to for m in mailoutbox] == [[user.email]]

    @pytest.mark.parametrize("case", ["unknown", "inactive", "unusable_password"])
    def test_no_mail_and_same_answer_when_no_resettable_account(self, client, mailoutbox, case):
        email = "kto@przyklad.pl"
        if case == "inactive":
            UserFactory(email=email, is_active=False)
        elif case == "unusable_password":
            account = UserFactory(email=email)
            account.set_unusable_password()
            account.save()

        response = request_link(client, email)

        assert response.status_code == 302 and response.url == SENT
        assert mailoutbox == []

    def test_invalid_email_rerenders_form(self, client, mailoutbox):
        response = request_link(client, "to-nie-email")
        assert response.status_code == 200 and "email" in response.context["form"].errors
        assert mailoutbox == []

    def test_logged_in_user_redirected(self, client, user):
        client.force_login(user)
        assert client.get(RESET).status_code == 302

    def test_smtp_failure_looks_like_success(self, client, user, monkeypatch):
        def broken_send(self, *args, **kwargs):
            raise OSError("SMTP down")

        monkeypatch.setattr("django.core.mail.EmailMultiAlternatives.send", broken_send)
        response = request_link(client, user.email)
        assert response.status_code == 302 and response.url == SENT

    def test_does_not_use_up_daily_email_allowance(self, client, user, mailoutbox):
        request_link(client, user.email)
        assert len(mailoutbox) == 1
        assert not EmailLog.objects.exists()

    def test_login_page_links_here(self, client):
        assert RESET in client.get(reverse("accounts:login")).content.decode()


class TestSetNewPassword:
    def _open_link(self, client, user, mailoutbox):
        request_link(client, user.email)
        response = client.get(link_from(mailoutbox[-1]))
        # Token moves into the session; the form lives at a URL without it.
        assert response.status_code == 302 and response.url.endswith("/ustaw")
        return response.url

    def test_full_flow_sets_password_and_logs_in(self, client, user, mailoutbox):
        form_url = self._open_link(client, user, mailoutbox)
        assert client.get(form_url).context["validlink"] is True

        response = client.post(
            form_url, {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD}
        )

        assert response.status_code == 302 and response.url == reverse("trees:map")
        assert get_user(client) == user
        user.refresh_from_db()
        assert user.check_password(NEW_PASSWORD) and not user.check_password(TEST_PASSWORD)

    def test_link_works_once(self, client, user, mailoutbox):
        form_url = self._open_link(client, user, mailoutbox)
        client.post(form_url, {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD})

        response = Client().get(link_from(mailoutbox[-1]))
        assert response.status_code == 200 and response.context["validlink"] is False
        assert "Ten link już nie działa" in response.content.decode()

    def test_link_expires_after_an_hour(self, client, user, mailoutbox, monkeypatch):
        request_link(client, user.email)
        later = default_token_generator._now() + timedelta(hours=1, minutes=1)
        monkeypatch.setattr(default_token_generator, "_now", lambda: later)

        response = client.get(link_from(mailoutbox[-1]))
        assert response.status_code == 200 and response.context["validlink"] is False

    def test_deactivated_account_cannot_reset(self, client, user, mailoutbox):
        request_link(client, user.email)
        user.is_active = False
        user.save()

        response = client.get(link_from(mailoutbox[-1]))
        assert response.context["validlink"] is False

    @pytest.mark.parametrize("uid", ["xxx", "bm90LWEtdXVpZA"])  # garbage, base64 of non-UUID
    def test_malformed_uid(self, client, uid):
        response = client.get(reverse("accounts:password-reset-confirm", args=[uid, "abc-def"]))
        assert response.status_code == 200 and response.context["validlink"] is False

    def test_other_sessions_logged_out(self, client, user, mailoutbox):
        other_device = Client()
        other_device.force_login(user)

        form_url = self._open_link(client, user, mailoutbox)
        client.post(form_url, {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD})

        assert not get_user(other_device).is_authenticated

    @pytest.mark.parametrize(
        ("password1", "password2", "message"),
        [
            ("krotkie", "krotkie", None),
            (NEW_PASSWORD, NEW_PASSWORD + "x", "Hasła nie są takie same."),
        ],
    )
    def test_password_validated(self, client, user, mailoutbox, password1, password2, message):
        form_url = self._open_link(client, user, mailoutbox)
        response = client.post(form_url, {"new_password1": password1, "new_password2": password2})

        assert response.status_code == 200
        assert "new_password2" in response.context["form"].errors
        if message:
            assert message in response.content.decode()
        user.refresh_from_db()
        assert user.check_password(TEST_PASSWORD)


class TestApi:
    def test_request_returns_202_for_known_and_unknown(self, client, user, mailoutbox):
        known = client.post(API_RESET, {"email": user.email}, content_type="application/json")
        unknown = client.post(
            API_RESET, {"email": "nikt@przyklad.pl"}, content_type="application/json"
        )

        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json()
        assert len(mailoutbox) == 1

    @pytest.mark.parametrize("body", ["{nie json", "{}", '{"email": "zly"}'])
    def test_request_bad_input(self, client, body):
        assert client.post(API_RESET, body, content_type="application/json").status_code == 400

    def test_confirm_sets_password_without_login(self, client, user, mailoutbox):
        client.post(API_RESET, {"email": user.email}, content_type="application/json")
        uid, token = uid_and_token(link_from(mailoutbox[-1]))

        response = client.post(
            API_CONFIRM,
            {"uid": uid, "token": token, "new_password1": NEW_PASSWORD,
             "new_password2": NEW_PASSWORD},
            content_type="application/json",
        )  # fmt: skip

        assert response.status_code == 204
        assert not get_user(client).is_authenticated
        user.refresh_from_db()
        assert user.check_password(NEW_PASSWORD)

        again = client.post(
            API_CONFIRM,
            {"uid": uid, "token": token, "new_password1": "inne-haslo-12345",
             "new_password2": "inne-haslo-12345"},
            content_type="application/json",
        )  # fmt: skip
        assert again.status_code == 400 and "detail" in again.json()

    def test_confirm_validation_errors(self, client, user):
        uid, token = uid_and_token(services.reset_link(user))
        response = client.post(
            API_CONFIRM,
            {"uid": uid, "token": token, "new_password1": "krotkie", "new_password2": "krotkie"},
            content_type="application/json",
        )
        assert response.status_code == 400 and "new_password2" in response.json()["errors"]

    def test_confirm_bad_token(self, client, user):
        uid, _ = uid_and_token(services.reset_link(user))
        response = client.post(
            API_CONFIRM,
            {"uid": uid, "token": "zly-token", "new_password1": NEW_PASSWORD,
             "new_password2": NEW_PASSWORD},
            content_type="application/json",
        )  # fmt: skip
        assert response.status_code == 400


class TestCsrf:
    @pytest.mark.parametrize("url", [RESET, API_RESET, API_CONFIRM])
    def test_post_without_token_rejected(self, user, url):
        response = Client(enforce_csrf_checks=True).post(
            url, {"email": user.email}, content_type="application/json"
        )
        assert response.status_code == 403


class TestRateLimit:
    def test_eleventh_request_from_ip_blocked_across_page_and_api(self, client):
        for _ in range(10):
            client.post(API_RESET, {"email": "x@przyklad.pl"}, content_type="application/json")
        assert request_link(client, "x@przyklad.pl").status_code == 429
        assert (
            client.post(API_RESET, {"email": "x@przyklad.pl"}, content_type="application/json")
        ).status_code == 429

    def test_separate_from_login_limit(self, client):
        for _ in range(10):
            request_link(client, "x@przyklad.pl")
        login = client.post(reverse("accounts:login"), {"username": "x@p.pl", "password": "x"})
        assert login.status_code == 200

    def test_at_most_three_mails_per_address_per_hour(self, user, mailoutbox):
        # Different IPs each time: the per-address limit holds on its own.
        for i in range(5):
            response = request_link(Client(REMOTE_ADDR=f"10.0.0.{i + 1}"), user.email)
            assert response.status_code == 302 and response.url == SENT
        assert len(mailoutbox) == 3
