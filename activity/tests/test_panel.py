"""The activity screen, its JSON twin and the CSV. Written before the code.

Access per role is pinned in `accounts/tests/test_authz_matrix.py`; this file checks what an
admin actually gets. The CSV goes through `panel/export.py`, so BOM, `;` and the decimal
comma are already covered there — here only the activity columns are.
"""

import pytest
from django.urls import reverse

from accounts.models import User
from activity.models import ActivityEvent
from factories import TreeFactory, UserFactory
from panel.export import ACTIVITY_HEADER, BOM, CSV_DELIMITER, activity_rows

pytestmark = pytest.mark.django_db

Kind = ActivityEvent.Kind


@pytest.fixture
def admin(client):
    person = UserFactory(role=User.Role.ADMIN, display_name="Katarzyna Malinowska")
    client.force_login(person)
    return person


@pytest.fixture
def history(db):
    anna = UserFactory(display_name="Anna Łęcka")
    tree = TreeFactory(species="Jabłoń – Ligol")
    ActivityEvent.objects.create(kind=Kind.LOGIN, user=anna)
    ActivityEvent.objects.create(kind=Kind.WATERING, user=anna, tree=tree)
    ActivityEvent.objects.create(kind=Kind.CARD_VIEW, tree=tree)
    return anna, tree


class TestPage:
    def test_shows_tiles_and_people(self, client, admin, history):
        anna, _ = history

        response = client.get(reverse("panel:activity"))

        assert response.status_code == 200
        assert response.context["tab"] == "activity"
        page = response.content.decode()
        assert "Logowania" in page
        assert anna.display_name in page

    def test_tab_is_in_the_panel_navigation(self, client, admin):
        page = client.get(reverse("panel:dashboard")).content.decode()

        assert reverse("panel:activity") in page

    def test_chart_has_no_inline_styles(self, client, admin, history):
        """Strict CSP: SVG geometry, never `style=` (CLAUDE.md, front-end rules)."""
        page = client.get(reverse("panel:activity")).content.decode()

        assert "<svg" in page
        assert "style=" not in page

    def test_chart_geometry_uses_a_decimal_point(self, client, admin, history):
        """Polish formatting turns 90.0 into "90,0" — the browser then drops every bar."""
        import re

        page = client.get(reverse("panel:activity")).content.decode()

        rects = re.findall(r"<rect ([^>]*)>", page)
        assert rects
        for attributes in rects:
            assert "," not in attributes

    def test_users_list_shows_last_login(self, client, admin):
        page = client.get(reverse("panel:users")).content.decode()

        assert "Ostatnie logowanie" in page


class TestApi:
    def test_returns_the_summary_as_json(self, client, admin, history):
        anna, _ = history

        data = client.get(reverse("admin-api:activity")).json()

        assert data["card_views_30"] == 1
        assert len(data["daily"]) == 30
        assert {"day", "logins", "interactions"} <= set(data["daily"][0])
        [row] = [row for row in data["people"] if row["display_name"] == anna.display_name]
        assert row["id"] == str(anna.pk)
        assert row["interactions_30"] == 1

    def test_people_carry_no_e_mail(self, client, admin, history):
        """The screen needs names, not addresses; the users list is where e-mails live."""
        data = client.get(reverse("admin-api:activity")).json()

        assert all("email" not in row for row in data["people"])


class TestCsv:
    def test_rows_newest_first_with_readable_kind(self, history):
        anna, tree = history

        rows = list(activity_rows())

        assert len(ACTIVITY_HEADER) == len(rows[0])
        kinds = [row[1] for row in rows]
        assert "Podlanie" in kinds
        assert "Wyświetlenie karty" in kinds
        watering = rows[kinds.index("Podlanie")]
        assert anna.display_name in watering
        assert tree.pk in watering  # raw values; format_value() turns them into text

    def test_anonymous_rows_have_an_empty_person(self, history):
        rows = list(activity_rows())

        card_view = next(row for row in rows if row[1] == "Wyświetlenie karty")
        assert card_view[2] in ("", None)

    def test_download(self, client, admin, history):
        response = client.get(reverse("admin-api:export-activity"))

        assert response.status_code == 200
        assert 'filename="aktywnosc-' in response["Content-Disposition"]
        body = b"".join(response.streaming_content).decode("utf-8")
        assert body.startswith(BOM)
        assert CSV_DELIMITER.join(ACTIVITY_HEADER) in body
        assert "Anna Łęcka" in body

    def test_export_page_links_the_new_file(self, client, admin):
        page = client.get(reverse("panel:export")).content.decode()

        assert reverse("admin-api:export-activity") in page
