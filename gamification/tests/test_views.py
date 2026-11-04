"""The achievements page, its JSON twin and the "Nowa odznaka!" toast.

Access per role lives in `accounts/tests/test_authz_matrix.py`.
"""

from datetime import timedelta

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from factories import TreeFactory, UserFactory
from gamification.models import UserBadge
from trees.models import Assignment
from trees.tests.factories import water

pytestmark = pytest.mark.django_db

PAGE = reverse("gamification:achievements")
API = reverse("me-api:achievements")


@pytest.fixture
def volunteer(client):
    person = UserFactory(display_name="Anna Kowalska", email="anna@przyklad.pl")
    client.force_login(person)
    return person


def toasts(response):
    return [str(message) for message in get_messages(response.wsgi_request)]


class TestPage:
    def test_newcomer_sees_level_one_and_an_invitation(self, client, volunteer):
        response = client.get(PAGE)

        assert response.status_code == 200
        page = response.content.decode()
        assert "Poziom 1" in page
        assert "Zacznij zbierać punkty" in page
        assert "Pierwsza kropla" in page  # locked badges are listed too, with how to earn them

    def test_shows_earned_badges_and_ranking(self, client, volunteer, tree):
        water(tree, volunteer)

        page = client.get(PAGE).content.decode()

        assert "Zdobyta" in page
        assert "Nowa!" in page
        assert "Anna Kowalska (Ty)" in page

    def test_new_marker_shows_once(self, client, volunteer, tree):
        water(tree, volunteer)
        client.get(PAGE)

        assert "Nowa!" not in client.get(PAGE).content.decode()

    def test_time_alone_earns_a_badge(self, client, volunteer, tree):
        """Thirty days of care is earned by waiting — the page awards it on the next visit."""
        Assignment.objects.create(
            tree=tree, user=volunteer, started_at=timezone.now() - timedelta(days=30)
        )

        client.get(PAGE)

        assert UserBadge.objects.filter(user=volunteer, code="faithful").exists()

    def test_no_inline_styles(self, client, volunteer, tree):
        """Strict CSP: the progress bar is a <progress>, not a width in style=."""
        water(tree, volunteer)

        page = client.get(PAGE).content.decode()

        assert "<progress" in page
        assert "style=" not in page

    def test_no_e_mail_on_the_page(self, client, volunteer, tree):
        other = UserFactory(email="sasiad@przyklad.pl")
        water(tree, other)

        page = client.get(PAGE).content.decode()

        assert "sasiad@przyklad.pl" not in page
        assert other.display_name in page

    def test_menu_links_the_page(self, client, volunteer):
        assert PAGE in client.get(reverse("trees:my")).content.decode()


class TestToast:
    def test_first_watering_announces_the_badge(self, client, volunteer, tree):
        response = client.post(reverse("trees:water", kwargs={"tree_id": tree.pk}))

        assert any("Pierwsza kropla" in message for message in toasts(response))

    def test_announced_only_once(self, client, volunteer, tree):
        url = reverse("trees:water", kwargs={"tree_id": tree.pk})
        client.post(url, follow=True)  # the card shows — and so uses up — the first toast

        response = client.post(url)

        assert not any("odznak" in message for message in toasts(response))

    def test_taking_care_announces_caretaker(self, client, volunteer):
        tree = TreeFactory()

        response = client.post(reverse("trees:take-care", kwargs={"tree_id": tree.pk}))

        assert any("Opiekun" in message for message in toasts(response))

    def test_thanks_and_badge_are_both_visible(self, client, volunteer):
        """Two toasts at once: a stack, not two fixed elements on the same spot."""
        tree = TreeFactory()

        page = client.post(
            reverse("trees:take-care", kwargs={"tree_id": tree.pk}), follow=True
        ).content.decode()

        assert 'class="toast-stack"' in page
        assert page.count('class="toast auto"') == 2
        assert 'id="toast"' not in page


class TestApi:
    def test_returns_level_badges_and_ranking(self, client, volunteer, tree):
        water(tree, volunteer)

        data = client.get(API).json()

        assert data["points"] > 0
        assert data["level"]["number"] == 1
        first_drop = next(badge for badge in data["badges"] if badge["code"] == "first_drop")
        assert first_drop["earned"] is True
        assert any(row["is_me"] for row in data["ranking"]["rows"])

    def test_carries_no_e_mail(self, client, volunteer, tree):
        water(tree, volunteer)

        body = client.get(API).content.decode()

        assert volunteer.email not in body

    def test_reading_does_not_mark_badges_seen(self, client, volunteer, tree):
        """The toast belongs to the page; an app polling the API must not swallow it."""
        water(tree, volunteer)

        client.get(API)

        assert UserBadge.objects.filter(user=volunteer, seen_at__isnull=True).exists()
