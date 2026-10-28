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


def test_topics_in_order_each_introduced_before_its_media(client):
    # Mentor's brief (2026-10-28): species, planting, care, films — the text before the graphic.
    html = client.get(URL).content.decode()

    topics = [
        ("Poznaj gatunki drzew", "Wybierz gatunek i poznaj go bliżej", None),
        ("Jak prawidłowo posadzić drzewo?", "Zobacz, jak zrobić to dobrze", INFOGRAPHICS[0]),
        ("Pielęgnacja drzew po posadzeniu", "Sprawdź, jak zadbać o swoje drzewo", INFOGRAPHICS[1]),
        ("Filmy", "Obejrzyj i sprawdź", "video/sadzenie-drzewa.mp4"),
    ]
    positions = []
    for heading, intro, media in topics:
        heading_at = html.index(f">{heading}")
        intro_at = html.index(intro)
        assert heading_at < intro_at
        if media:
            assert intro_at < html.index(f'src="{static(media)}"')
        positions.append(heading_at)

    assert positions == sorted(positions)


def test_species_topic_says_descriptions_are_coming(client):
    # No species content exists yet; the page must not look like the list failed to load.
    html = client.get(URL).content.decode()

    assert "Opisy gatunków są w przygotowaniu" in html


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
