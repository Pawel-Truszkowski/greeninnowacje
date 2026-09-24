"""Who am I logged in as (PoC: "🔓 Zalogowano: Anna Kowalska").

Until now the only sign of being logged in was the "Wyloguj" button. On a shared phone
at a planting event that is not enough — a volunteer must see whose account records the
watering, because the entry is permanent (spec §3: waterings are append-only).
"""

import pytest
from django.urls import reverse

from factories import TreeFactory, UserFactory
from trees.tests.factories import assign

pytestmark = pytest.mark.django_db

# The lock emoji belongs to the pill only — the header button says "Zalogowano" in
# its tooltip, which would make a looser check ambiguous.
PILL = "🔓 Zalogowano:"


@pytest.fixture
def volunteer(client):
    user = UserFactory(display_name="Anna Kowalska")
    client.force_login(user)
    return user


@pytest.fixture
def tree():
    return TreeFactory()


def page_urls(tree):
    return {
        "moje drzewa": reverse("trees:my"),
        "rejestracja drzewa": reverse("trees:register"),
        "karta drzewa": reverse("trees:card", kwargs={"tree_id": tree.pk}),
    }


class TestPill:
    @pytest.mark.parametrize("page", ["moje drzewa", "rejestracja drzewa", "karta drzewa"])
    def test_shown_on_pages_for_logged_in_users(self, client, volunteer, tree, page):
        content = client.get(page_urls(tree)[page]).content.decode()

        assert PILL in content
        assert "Anna Kowalska" in content

    def test_not_shown_to_guests(self, client, tree):
        content = client.get(reverse("trees:card", kwargs={"tree_id": tree.pk})).content.decode()

        assert PILL not in content

    def test_map_stays_clean(self, client, volunteer):
        """The map is mostly map; the header alone carries the account there."""
        content = client.get(reverse("trees:map")).content.decode()

        assert PILL not in content


class TestHeader:
    def test_header_shows_the_name(self, client, volunteer, tree):
        content = client.get(reverse("trees:map")).content.decode()

        assert "Anna Kowalska" in content

    def test_header_has_no_name_for_guests(self, client):
        content = client.get(reverse("trees:map")).content.decode()

        assert "Wyloguj" not in content
        assert "Zalogowano" not in content


def test_display_name_is_escaped(client):
    """display_name is user input — it must never reach the page as markup."""
    user = UserFactory(display_name="<script>alert('xss')</script>")
    client.force_login(user)
    tree = TreeFactory()
    assign(tree, user)

    content = client.get(reverse("trees:my")).content.decode()

    assert "<script>alert" not in content
    assert "&lt;script&gt;alert" in content
