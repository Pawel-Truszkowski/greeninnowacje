"""QR codes for species pages: stickers on saplings handed out to residents.

The PNG is public, like the page it points at; the printable sheet is for coordinators and
admins, who hand the saplings out. A printed sticker cannot be recalled, so the tests pin
down where the code leads and that hidden guides — whose page is a 404 — never get one.
"""

import pytest
from django.urls import reverse

from accounts.models import User
from education import views
from education.models import SpeciesGuide
from education.qr import species_page_url
from education.services import save_guide
from factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def guide():
    return SpeciesGuide.objects.get(slug="lipa-drobnolistna")


@pytest.fixture
def log_in(client):
    def make(role):
        client.force_login(UserFactory(role=role))
        return client

    return make


def qr_url(guide):
    return reverse("education:species-qr", args=[guide.slug])


def stickers_url(guide):
    return reverse("education:species-stickers", args=[guide.slug])


def hide(guide):
    SpeciesGuide.objects.filter(pk=guide.pk).update(is_published=False)


def test_species_page_url_is_absolute(settings, guide):
    settings.APP_BASE_URL = "https://drzewa.example.org"

    assert species_page_url(guide) == (
        "https://drzewa.example.org/baza-wiedzy/gatunki/lipa-drobnolistna"
    )


def test_species_page_url_resolves_to_the_public_page(client, settings, guide):
    path = species_page_url(guide).removeprefix(settings.APP_BASE_URL)

    assert client.get(path).status_code == 200


def test_another_species_name_keeps_the_printed_address(guide):
    """The slug is set once — stickers already on saplings must keep working."""
    before = species_page_url(guide)

    renamed = save_guide(guide, "Lipa szerokolistna")

    assert renamed.name == "Lipa szerokolistna"
    assert species_page_url(renamed) == before


class TestQrImage:
    def test_anyone_gets_a_png(self, client, guide):
        response = client.get(qr_url(guide))

        assert response.status_code == 200
        assert response["Content-Type"] == "image/png"
        assert response.content.startswith(b"\x89PNG")
        assert response["Cache-Control"] == f"public, max-age={views.QR_CACHE_SECONDS}"
        assert "Content-Disposition" not in response

    def test_encodes_the_species_page(self, client, guide, monkeypatch):
        encoded = []
        monkeypatch.setattr(views, "qr_png", lambda url: encoded.append(url) or b"png")

        client.get(qr_url(guide))

        assert encoded == [species_page_url(guide)]

    def test_download_names_the_file_after_the_slug(self, client, guide):
        response = client.get(f"{qr_url(guide)}?download=1")

        assert response["Content-Disposition"] == (
            'attachment; filename="qr-lipa-drobnolistna.png"'
        )

    def test_hidden_guide_has_no_code(self, client, guide):
        hide(guide)

        assert client.get(qr_url(guide)).status_code == 404


class TestStickerSheet:
    @pytest.mark.parametrize("role", [User.Role.COORDINATOR, User.Role.ADMIN])
    def test_shows_a_full_sheet_for_the_species(self, log_in, guide, role):
        response = log_in(role).get(stickers_url(guide))

        body = response.content.decode()
        assert response.status_code == 200
        assert body.count('class="sticker"') == views.STICKERS_PER_SHEET
        assert body.count(f'src="{qr_url(guide)}"') == views.STICKERS_PER_SHEET
        assert guide.name in body and guide.latin_name in body
        assert "localhost:8000/baza-wiedzy/gatunki/lipa-drobnolistna" in body

    def test_print_button_needs_no_inline_script(self, log_in, guide):
        body = log_in(User.Role.COORDINATOR).get(stickers_url(guide)).content.decode()

        assert "js/print.js" in body
        assert "onclick" not in body

    def test_hidden_guide_has_no_sheet(self, log_in, guide):
        hide(guide)

        assert log_in(User.Role.ADMIN).get(stickers_url(guide)).status_code == 404


class TestSpeciesPage:
    def species_page(self, client, guide):
        return client.get(reverse("education:species", args=[guide.slug])).content.decode()

    def test_everyone_can_download_the_code(self, client, guide):
        body = self.species_page(client, guide)

        assert f'src="{qr_url(guide)}"' in body
        assert f"{qr_url(guide)}?download=1" in body

    @pytest.mark.parametrize("role", [None, User.Role.VOLUNTEER])
    def test_sticker_sheet_link_is_hidden_from_others(self, client, log_in, guide, role):
        page_client = log_in(role) if role else client

        assert stickers_url(guide) not in self.species_page(page_client, guide)

    @pytest.mark.parametrize("role", [User.Role.COORDINATOR, User.Role.ADMIN])
    def test_coordinators_and_admins_see_the_sticker_sheet_link(self, log_in, guide, role):
        assert stickers_url(guide) in self.species_page(log_in(role), guide)


class TestPanelList:
    def test_published_guide_offers_qr(self, log_in, guide):
        body = log_in(User.Role.ADMIN).get(reverse("panel:species")).content.decode()

        assert f"{qr_url(guide)}?download=1" in body
        assert stickers_url(guide) in body

    def test_hidden_guide_offers_no_qr(self, log_in, guide):
        hide(guide)

        body = log_in(User.Role.ADMIN).get(reverse("panel:species")).content.decode()

        assert qr_url(guide) not in body
        assert "Opublikuj, aby pobrać kod QR" in body
