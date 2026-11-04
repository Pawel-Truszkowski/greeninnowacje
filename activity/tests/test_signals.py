"""Login, failed login, logout and sign-up as activity events. Written before the code.

Auth events come from Django's signals, not from our views, so both entry points — the HTML
form and the JSON API — are covered by one mechanism. These tests go through both doors on
purpose: a row that only appears for one of them is the bug this design exists to prevent.
"""

import pytest
from django.urls import reverse

from accounts.models import User
from activity.models import ActivityEvent
from factories import TEST_PASSWORD, UserFactory

pytestmark = pytest.mark.django_db

Kind = ActivityEvent.Kind

LOGIN = reverse("accounts:login")
LOGOUT = reverse("accounts:logout")
REGISTER = reverse("accounts:register")
API_LOGIN = reverse("auth-api:api-login")
API_LOGOUT = reverse("auth-api:api-logout")
API_REGISTER = reverse("auth-api:api-register")

NEW_ACCOUNT = {
    "email": "nowa@przyklad.pl",
    "display_name": "Nowa Osoba",
    "password": "bardzo-dlugie-haslo",
}


def events(kind):
    return list(ActivityEvent.objects.filter(kind=kind))


class TestLogin:
    def test_html_login_records_one_event_for_that_user(self, client, user):
        client.post(LOGIN, {"username": user.email, "password": TEST_PASSWORD})

        [event] = events(Kind.LOGIN)
        assert event.user == user
        assert event.tree is None

    def test_api_login_records_one_event_for_that_user(self, client, user):
        client.post(
            API_LOGIN,
            {"email": user.email, "password": TEST_PASSWORD},
            content_type="application/json",
        )

        [event] = events(Kind.LOGIN)
        assert event.user == user

    def test_force_login_counts_too(self, client, user):
        """`force_login` fires `user_logged_in` like a real login — tests rely on it below."""
        client.force_login(user)

        assert len(events(Kind.LOGIN)) == 1


class TestFailedLogin:
    def test_wrong_password_is_recorded_without_a_user(self, client, user):
        """No user: knowing whose account was attacked tells a stranger the e-mail exists."""
        client.post(LOGIN, {"username": user.email, "password": "zle-haslo-123"})

        [event] = events(Kind.LOGIN_FAILED)
        assert event.user is None
        assert not events(Kind.LOGIN)

    def test_api_wrong_password_is_recorded_too(self, client, user):
        client.post(
            API_LOGIN,
            {"email": user.email, "password": "zle-haslo-123"},
            content_type="application/json",
        )

        assert len(events(Kind.LOGIN_FAILED)) == 1

    def test_typed_credentials_are_not_stored_anywhere(self, client):
        """People type their password into the e-mail field. Neither may land in the log."""
        secret = "moje-tajne-haslo-w-polu-email"
        client.post(LOGIN, {"username": secret, "password": "cokolwiek-123"})

        row = ActivityEvent.objects.filter(kind=Kind.LOGIN_FAILED).values().get()
        assert secret not in " ".join(str(value) for value in row.values())


class TestLogout:
    @pytest.mark.parametrize("url", [LOGOUT, API_LOGOUT])
    def test_logout_records_the_user_who_left(self, client, user, url):
        client.force_login(user)

        client.post(url)

        [event] = events(Kind.LOGOUT)
        assert event.user == user

    def test_anonymous_logout_records_nothing(self, client):
        client.post(LOGOUT)

        assert not events(Kind.LOGOUT)


class TestSignup:
    def test_html_registration_records_signup_and_login(self, client):
        client.post(REGISTER, NEW_ACCOUNT)

        person = User.objects.get(email=NEW_ACCOUNT["email"])
        assert [event.user for event in events(Kind.SIGNUP)] == [person]
        assert [event.user for event in events(Kind.LOGIN)] == [person]

    def test_api_registration_records_signup(self, client):
        client.post(API_REGISTER, NEW_ACCOUNT, content_type="application/json")

        assert len(events(Kind.SIGNUP)) == 1

    def test_accounts_created_outside_the_form_count_as_signups(self):
        """`post_save`, not the view: createsuperuser and the demo seed are sign-ups too."""
        person = UserFactory()

        assert [event.user for event in events(Kind.SIGNUP)] == [person]

    def test_editing_an_account_is_not_a_signup(self, user):
        user.display_name = "Nowe imię"
        user.save()

        assert len(events(Kind.SIGNUP)) == 1
