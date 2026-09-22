import pytest
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError

from accounts.models import User
from factories import TEST_PASSWORD, UserFactory

pytestmark = pytest.mark.django_db


def test_email_is_stored_lowercase():
    user = UserFactory(email="  Anna.K@Przyklad.PL ")
    user.refresh_from_db()
    assert user.email == "anna.k@przyklad.pl"


def test_email_unique_regardless_of_case():
    User.objects.create_user("anna@przyklad.pl", TEST_PASSWORD, "Anna")
    with pytest.raises(ValidationError):
        User.objects.create_user("ANNA@przyklad.pl", TEST_PASSWORD, "Anna 2")


def test_login_with_differently_cased_email():
    user = UserFactory(email="marta@przyklad.pl")
    assert authenticate(email="Marta@Przyklad.pl", password=TEST_PASSWORD) == user


def test_inactive_user_cannot_log_in():
    UserFactory(email="jan@przyklad.pl", is_active=False)
    assert authenticate(email="jan@przyklad.pl", password=TEST_PASSWORD) is None


def test_password_hashed_with_argon2():
    assert UserFactory().password.startswith("argon2")


def test_new_user_is_volunteer_by_default():
    user = User.objects.create_user("nowy@przyklad.pl", TEST_PASSWORD, "Nowy")
    assert user.role == User.Role.VOLUNTEER
    assert not user.is_app_admin
    assert not user.is_staff


def test_superuser_is_app_admin():
    user = User.objects.create_superuser("szef@przyklad.pl", TEST_PASSWORD, "Szef")
    assert user.is_app_admin and user.is_staff and user.is_superuser
