import pytest
from django.urls import reverse

from factories import TreeFactory
from trees.qr import qr_png, tree_card_url

pytestmark = pytest.mark.django_db

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def tree():
    return TreeFactory()


def qr_url(tree):
    return reverse("trees-api:qr", kwargs={"tree_id": tree.pk})


def test_returns_png(client, tree):
    response = client.get(qr_url(tree))

    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
    assert response.content.startswith(PNG_SIGNATURE)
    assert "max-age" in response["Cache-Control"]


def test_encodes_public_card_url(client, tree, settings, monkeypatch):
    settings.APP_BASE_URL = "https://drzewa.greeninnowacje.pl"
    encoded = []
    monkeypatch.setattr("trees.api.qr_png", lambda url: encoded.append(url) or b"")

    client.get(qr_url(tree))

    assert encoded == [f"https://drzewa.greeninnowacje.pl/drzewo/{tree.pk}"]


def test_download_sets_attachment_header(client, tree):
    response = client.get(qr_url(tree), {"download": "1"})
    assert f'attachment; filename="drzewo-{tree.pk}.png"' == response["Content-Disposition"]


def test_card_url_matches_page_route(tree):
    assert tree_card_url(tree.pk).endswith(reverse("trees:card", kwargs={"tree_id": tree.pk}))


def test_qr_png_is_deterministic():
    assert qr_png("https://example.test/drzewo/1") == qr_png("https://example.test/drzewo/1")
