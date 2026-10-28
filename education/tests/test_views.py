"""The knowledge base page: public, server-rendered, film and infographics served from static."""

import pytest
from django.templatetags.static import static
from django.urls import reverse

pytestmark = pytest.mark.django_db

URL = reverse("education:index")

INFOGRAPHICS = [
    "img/jak-prawidlowo-posadzic-drzewo.jpg",
    "img/pielegnacja-drzewa-po-posadzeniu.jpg",
]


def test_url_is_baza_wiedzy():
    assert URL == "/baza-wiedzy"


def test_anonymous_sees_text_and_film(client):
    response = client.get(URL)

    assert response.status_code == 200
    html = response.content.decode()
    assert "Baza wiedzy" in html
    assert "„Drzewo dla Pokoleń”" in html
    assert f'src="{static("video/sadzenie-drzewa.mp4")}"' in html
    assert 'type="video/mp4"' in html


def test_film_does_not_download_before_play(client):
    # The page is open to everyone, often on mobile data; the film is tens of megabytes.
    html = client.get(URL).content.decode()

    assert 'preload="metadata"' in html


@pytest.mark.parametrize("path", INFOGRAPHICS)
def test_page_shows_infographic(client, path):
    html = client.get(URL).content.decode()

    assert f'src="{static(path)}"' in html
    # Linked at full size, so a phone can zoom into the small print.
    assert f'href="{static(path)}"' in html


def test_infographics_are_lazy_and_described(client):
    html = client.get(URL).content.decode()

    assert html.count('loading="lazy"') >= len(INFOGRAPHICS)
    assert 'alt=""' not in html


def test_infographics_have_text_version(client):
    # The steps live in the images; screen readers and search need them as text (WCAG 1.1.1).
    html = client.get(URL).content.decode()

    assert html.count("<details") >= len(INFOGRAPHICS)
    assert "szyjka korzeniowa" in html  # planting, step 3
    assert "Kontrola palików i wiązań" in html  # care, step 2


def test_old_url_is_gone(client):
    # Renamed without a redirect, by decision (2026-10-28).
    assert client.get("/materialy-edukacyjne").status_code == 404


@pytest.mark.parametrize("logged_in", [False, True])
def test_nav_links_to_knowledge_base(client, user, logged_in):
    if logged_in:
        client.force_login(user)

    html = client.get(reverse("trees:map")).content.decode()

    assert f'href="{URL}"' in html


def test_nav_marks_knowledge_base_active(client):
    html = client.get(URL).content.decode()

    assert f'<a href="{URL}" class="active" aria-current="page">Baza wiedzy</a>' in html
