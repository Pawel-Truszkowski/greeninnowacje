"""Template rules that no other test would notice being broken.

Django's `{# #}` is a single-line comment. Spanning one over two lines does not fail, does
not warn — it renders the comment as text. That shipped inside the volunteer e-mail and on
the tree card before anyone noticed, which is exactly the kind of thing a cheap scan catches
and a feature test never will.
"""

import re
from pathlib import Path

import pytest

TEMPLATES = sorted((Path(__file__).resolve().parent.parent.parent / "templates").rglob("*.html"))
MULTILINE_COMMENT = re.compile(r"\{#[^#]*?\n.*?#\}", re.S)


def test_there_are_templates_to_scan():
    assert TEMPLATES, "Nie znaleziono szablonów — ścieżka się rozjechała"


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda p: p.name)
def test_no_multiline_django_comment(path):
    found = MULTILINE_COMMENT.findall(path.read_text(encoding="utf-8"))

    assert not found, (
        f"{path.name}: {{# #}} działa tylko w jednej linii — wieloliniowy komentarz "
        f"wyrenderuje się jako tekst. Użyj {{% comment %}}. Znaleziono: {found[0][:60]}…"
    )
