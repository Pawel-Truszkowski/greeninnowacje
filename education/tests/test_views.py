"""The knowledge base: the page itself, the species guides and their public images."""

import pytest
from django.templatetags.static import static
from django.urls import reverse

from education.models import SpeciesGuide

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
    # Infographics need a description. Species card photos may not: the species name is
    # text inside the same link, so an alt would only make screen readers say it twice.
    for path in INFOGRAPHICS:
        tag = html[html.index(f'src="{static(path)}"') :].split(">", 1)[0]
        assert 'alt="Infografika' in tag


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


class TestSpeciesGrid:
    def test_lists_every_published_guide_with_link_and_photo(self, client):
        html = client.get(URL).content.decode()

        for guide in SpeciesGuide.objects.all():
            assert f'href="{reverse("education:species", args=[guide.slug])}"' in html
            assert reverse("education:species-image", args=[guide.slug, "miniatura"]) in html
            assert guide.latin_name in html
        assert "Opisy gatunków są w przygotowaniu" not in html

    def test_unpublished_guide_is_not_listed(self, client):
        SpeciesGuide.objects.filter(slug="olsza-czarna").update(is_published=False)

        html = client.get(URL).content.decode()

        assert "olsza-czarna" not in html

    def test_without_guides_says_descriptions_are_coming(self, client):
        # The page must not look like the list failed to load.
        SpeciesGuide.objects.update(is_published=False)

        html = client.get(URL).content.decode()

        assert "Opisy gatunków są w przygotowaniu" in html


def species_url(slug):
    return reverse("education:species", args=[slug])


class TestSpeciesPage:
    def test_shows_infographic_linked_at_full_size(self, client):
        guide = SpeciesGuide.objects.get(slug="lipa-drobnolistna")
        image = reverse("education:species-image", args=[guide.slug, "infografika"])

        html = client.get(species_url(guide.slug)).content.decode()

        assert f'src="{image}?v={guide.version}"' in html
        assert f'href="{image}?v={guide.version}"' in html
        assert 'width="1448" height="1086"' in html

    def test_carries_the_infographic_as_text(self, client):
        # WCAG 1.1.1: the image's text must reach screen readers and search.
        html = client.get(species_url("lipa-drobnolistna")).content.decode()

        assert "<h1" in html and "Lipa drobnolistna" in html
        assert "Tilia cordata" in html
        assert "<details" in html
        assert "Cenna dla zapylaczy" in html  # trait
        assert "Tolerancja na światło" in html  # parameter
        assert "z dala od linii energetycznych" in html  # where to plant
        assert "ograniczonej przestrzeni do rozrostu korony" in html  # dislikes

    def test_blank_birch_cells_are_not_shown(self, client):
        html = client.get(species_url("brzoza-brodawkowata")).content.decode()

        assert "Szerokość korony" not in html

    def test_pager_wraps_around(self, client):
        html = client.get(species_url("dab-szypulkowy")).content.decode()

        assert f'href="{species_url("olsza-czarna")}" rel="prev"' in html
        assert f'href="{species_url("dab-bezszypulkowy")}" rel="next"' in html

    def test_nav_marks_knowledge_base_without_claiming_current_page(self, client):
        html = client.get(species_url("klon-polny")).content.decode()

        assert f'<a href="{URL}" class="active">Baza wiedzy</a>' in html

    @pytest.mark.parametrize("slug", ["nie-ma-takiego", "olsza-czarna"])
    def test_unknown_or_unpublished_is_404(self, client, slug):
        SpeciesGuide.objects.filter(slug="olsza-czarna").update(is_published=False)

        assert client.get(species_url(slug)).status_code == 404


class TestSpeciesImage:
    @pytest.mark.parametrize("kind", ["infografika", "miniatura"])
    def test_serves_jpeg_publicly_with_caching(self, client, kind):
        response = client.get(reverse("education:species-image", args=["klon-polny", kind]))

        assert response.status_code == 200
        assert response["Content-Type"] == "image/jpeg"
        assert response["Cache-Control"] == "public, max-age=86400"
        assert b"".join(response.streaming_content)[:2] == b"\xff\xd8"  # JPEG magic

    def test_unknown_kind_is_404(self, client):
        url = reverse("education:species-image", args=["klon-polny", "zdjecie"])

        assert client.get(url).status_code == 404

    def test_unpublished_is_404(self, client):
        SpeciesGuide.objects.filter(slug="klon-polny").update(is_published=False)
        url = reverse("education:species-image", args=["klon-polny", "infografika"])

        assert client.get(url).status_code == 404


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
