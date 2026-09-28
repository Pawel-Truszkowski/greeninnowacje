"""The e-mails as artefacts: both parts present, Polish intact, tone as spec §5.3 asks.

The HTML alternative is the easiest thing to lose silently — a mail client would simply show
the plain text and nobody would notice the styled version stopped being attached.
"""

from datetime import date

import pytest

from factories import LocalityFactory, TreeFactory, UserFactory
from notifications.services import (
    ADMIN_TEMPLATE,
    VOLUNTEER_TEMPLATE,
    admin_digest,
    render,
    volunteer_digest,
)
from trees.models import Tree
from trees.tests.factories import assign

pytestmark = pytest.mark.django_db

DAY = date(2026, 9, 28)


@pytest.fixture
def overview():
    return {
        "localities": [{"name": "Sierpc", "urgent": 3, "orphans": 1}],
        "orphans": [TreeFactory(status=Tree.Status.URGENT)],
        "urgent_total": 3,
    }


def parts(message):
    return message.body, message.alternatives[0][0]


class TestVolunteerEmail:
    @pytest.fixture
    def message(self):
        volunteer = UserFactory(display_name="Anna")
        tree = TreeFactory(
            status=Tree.Status.URGENT,
            species="Jabłoń – Ligol",
            locality=LocalityFactory(name="Żółkiewka"),
        )
        assign(tree, volunteer)
        return render(volunteer_digest(volunteer, [tree]))

    def test_has_both_a_text_body_and_an_html_alternative(self, message):
        assert message.body.strip()
        assert message.alternatives[0][1] == "text/html"

    def test_polish_characters_survive_in_both_parts(self, message):
        for part in parts(message):
            assert "Jabłoń – Ligol" in part
            assert "Żółkiewka" in part

    def test_addresses_the_volunteer_by_name(self, message):
        assert "Anna" in message.body

    def test_tone_is_inviting_not_accusing(self, message):
        """Spec §5.3: „Twoje drzewa czekają na Ciebie", nie „zaniedbałeś"."""
        for part in parts(message):
            lowered = part.lower()
            assert "czekają na ciebie" in lowered
            for blaming in ("zaniedb", "zapomniał", "zaległ"):
                assert blaming not in lowered


class TestAdminEmail:
    def test_personal_section_only_when_the_admin_has_trees(self, overview):
        admin = UserFactory(role="admin", display_name="Katarzyna")

        without = render(admin_digest(admin, overview, [], DAY))
        with_own = render(
            admin_digest(admin, overview, [TreeFactory(species="Grusza – Konferencja")], DAY)
        )

        # Case-insensitively: the text part shouts its section headings, the HTML one does not.
        assert "twoje drzewa" not in without.body.lower()
        assert "twoje drzewa" in with_own.body.lower()
        assert "Grusza – Konferencja" in with_own.body

    def test_orphan_section_is_highlighted(self, overview):
        admin = UserFactory(role="admin")

        message = render(admin_digest(admin, overview, [], DAY))

        for part in parts(message):
            assert "bez opiekuna" in part.lower()

    def test_says_so_when_every_urgent_tree_has_a_caretaker(self, overview):
        admin = UserFactory(role="admin")
        overview["orphans"] = []

        message = render(admin_digest(admin, overview, [], DAY))

        for part in parts(message):
            assert "mają opiekuna" in part


def test_template_names_match_the_files_on_disk():
    """A renamed template would otherwise fail at 07:30, in a log nobody reads."""
    from django.template.loader import get_template

    for name in (VOLUNTEER_TEMPLATE, ADMIN_TEMPLATE):
        for extension in ("txt", "html"):
            assert get_template(f"emails/{name}.{extension}")
