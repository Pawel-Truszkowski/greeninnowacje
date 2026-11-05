"""„Co nowego" in the panel: CHANGELOG.md read from the running image.

Replaced a link to the GitHub Release, which was a 404 until CI had made the release —
locally always, and for a few minutes after every version bump.
"""

import pytest
from django.urls import reverse

from accounts.models import User
from core.version import APP_VERSION
from factories import UserFactory
from panel.changelog import load_changelog, parse_changelog

TEXT = """# Historia zmian

Wstęp dla programistów, z [linkiem](https://example.com).

## [2.1.0] — 2026-12-01

Krótki wstęp do wersji.

### Dodano
- **Coś nowego** — z opisem,
  który zajmuje dwie linie.
- Polecenie `uv lock`.

### Naprawiono
- Poprawka.

## [2.0.0] — 2026-11-04

- Punkt bez grupy.
"""


class TestParser:
    def test_versions_in_file_order_without_the_file_intro(self):
        releases = parse_changelog(TEXT)

        assert [(r.version, r.date) for r in releases] == [
            ("2.1.0", "2026-12-01"),
            ("2.0.0", "2026-11-04"),
        ]
        assert "programistów" not in str([r.intro for r in releases])

    def test_groups_items_and_intro(self):
        release = parse_changelog(TEXT)[0]

        assert [str(p) for p in release.intro] == ["Krótki wstęp do wersji."]
        assert [g.title for g in release.groups] == ["Dodano", "Naprawiono"]
        assert len(release.groups[0].items) == 2

    def test_an_indented_line_continues_the_item(self):
        item = str(parse_changelog(TEXT)[0].groups[0].items[0])

        assert item == "<strong>Coś nowego</strong> — z opisem, który zajmuje dwie linie."

    def test_inline_code(self):
        assert str(parse_changelog(TEXT)[0].groups[0].items[1]) == "Polecenie <code>uv lock</code>."

    def test_an_item_without_a_group_gets_an_untitled_one(self):
        [group] = parse_changelog(TEXT)[1].groups

        assert group.title == ""
        assert [str(i) for i in group.items] == ["Punkt bez grupy."]

    def test_markup_in_the_file_is_escaped(self):
        """Only ** and ` become HTML; anything else in the file is text."""
        [release] = parse_changelog('## [1.0.0]\n- <script>alert(1)</script> & **"x"**\n')

        item = str(release.groups[0].items[0])

        assert "<script>" not in item
        assert "&lt;script&gt;" in item
        assert "<strong>&quot;x&quot;</strong>" in item

    def test_the_real_changelog_starts_with_the_current_version(self):
        assert load_changelog()[0].version == APP_VERSION


@pytest.mark.django_db
class TestPage:
    def test_shows_every_version_and_marks_the_current_one(self, client):
        client.force_login(UserFactory(role=User.Role.ADMIN))

        response = client.get(reverse("panel:changelog"))

        assert response.status_code == 200
        page = response.content.decode()
        assert f"Wersja {APP_VERSION}" in page
        assert "Wersja 1.0.0" in page
        assert "obecna" in page
        assert "style=" not in page
