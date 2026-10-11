"""Brand and EU funding bar on every page.

The funding bar is a grant obligation (FERS visibility rules), not decoration: a template
refactor that drops it from `base.html` would pass every feature test and still breach the
grant agreement. The old name "Green Innowacje" must not come back in UI copy or e-mails.
"""

from pathlib import Path

import pytest
from django.urls import reverse

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
OLD_NAME = "Green Innowacje"
FUNDING_ALT = (
    "Fundusze Europejskie dla Rozwoju Społecznego, Rzeczpospolita Polska, "
    "Dofinansowane przez Unię Europejską, SENSE"
)


@pytest.mark.django_db
@pytest.mark.parametrize("logged_in", [False, True], ids=["guest", "volunteer"])
@pytest.mark.parametrize("name", ["trees:map", "accounts:login"])
def test_page_shows_funding_bar_and_brand(client, user, name, logged_in):
    if logged_in:
        client.force_login(user)

    html = client.get(reverse(name), follow=True).content.decode()

    assert "img/fe-belka" in html, "Brak belki FE — obowiązek promocyjny projektu"
    assert f'alt="{FUNDING_ALT}"' in html, "Belka FE musi mieć pełny tekst alternatywny"
    assert "GREENowacje" in html
    assert "Drzewo dla Pokoleń" in html
    assert OLD_NAME not in html


TEMPLATE_FILES = sorted(p for p in TEMPLATES_DIR.rglob("*") if p.suffix in {".html", ".txt"})


@pytest.mark.parametrize("path", TEMPLATE_FILES, ids=lambda p: str(p.relative_to(TEMPLATES_DIR)))
def test_no_old_brand_name_in_templates(path):
    assert OLD_NAME not in path.read_text(encoding="utf-8"), f"{path.name}: stara nazwa marki"
