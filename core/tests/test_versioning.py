"""The version as a checked artefact, like the crontab in `test_crontab.py`.

A version number rots quietly: bump it without a changelog entry and the release notes come
out empty; bump it without `uv lock` and CI fails on `uv sync --locked` far from the cause.
These tests say what is wrong, in the change that broke it.
"""

import re
import tomllib

import pytest
from django.urls import reverse

from accounts.models import User
from core.version import (
    APP_VERSION,
    BASE_DIR,
    CHANGELOG,
    PYPROJECT,
    changelog_section,
    read_version,
)
from factories import UserFactory

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


class TestSingleSourceOfTruth:
    def test_version_is_major_minor_patch(self):
        assert SEMVER.match(APP_VERSION), f"Wersja {APP_VERSION!r} nie ma postaci X.Y.Z"

    def test_comes_from_pyproject(self):
        assert APP_VERSION == read_version(PYPROJECT)

    def test_lockfile_has_the_same_version(self):
        lock = tomllib.loads((BASE_DIR / "uv.lock").read_text(encoding="utf-8"))
        [project] = [pkg for pkg in lock["package"] if pkg["name"] == "greeninnowacje"]

        assert project["version"] == APP_VERSION, (
            "uv.lock ma inną wersję niż pyproject.toml — uruchom `uv lock`"
        )

    def test_changelog_describes_the_current_version(self):
        notes = changelog_section(CHANGELOG.read_text(encoding="utf-8"), APP_VERSION)

        assert notes, f"CHANGELOG.md nie ma sekcji „## [{APP_VERSION}]” — opisz, co się zmieniło"

    def test_newest_changelog_section_is_the_current_version(self):
        """A section added for a version nobody bumped to would never be released."""
        first = re.search(r"^## \[([^\]]+)\]", CHANGELOG.read_text(encoding="utf-8"), re.M)

        assert first[1] == APP_VERSION


class TestChangelogSection:
    TEXT = """# Historia zmian

Wstęp.

## [2.1.0] — 2026-12-01

### Dodano
- Coś nowego.

## [2.0.0] — 2026-11-04

- Starsze.
"""

    def test_returns_the_body_without_the_heading(self):
        assert changelog_section(self.TEXT, "2.1.0") == "### Dodano\n- Coś nowego."

    def test_stops_at_the_next_version(self):
        assert changelog_section(self.TEXT, "2.0.0") == "- Starsze."

    def test_missing_version_is_none(self):
        assert changelog_section(self.TEXT, "9.9.9") is None

    def test_a_version_is_not_matched_by_its_prefix(self):
        assert changelog_section(self.TEXT, "2.1") is None


@pytest.mark.django_db
class TestShown:
    def test_footer_shows_the_number_to_everyone(self, client):
        page = client.get(reverse("trees:map")).content.decode()

        assert f"wersja {APP_VERSION}" in page

    def test_footer_does_not_show_the_commit(self, client, monkeypatch):
        monkeypatch.setattr("core.context_processors.APP_COMMIT", "abc1234")

        page = client.get(reverse("trees:map")).content.decode()

        assert "abc1234" not in page

    def test_panel_shows_commit_and_links_whats_new(self, client, monkeypatch):
        monkeypatch.setattr("core.context_processors.APP_COMMIT", "abc1234")
        client.force_login(UserFactory(role=User.Role.ADMIN))

        page = client.get(reverse("panel:dashboard")).content.decode()

        assert "abc1234" in page
        assert reverse("panel:changelog") in page
        assert "github.com" not in page  # a link to a release that may not exist yet was a 404
