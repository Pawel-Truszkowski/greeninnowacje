"""The education materials page: public, server-rendered, the film served from static."""

import pytest
from django.templatetags.static import static
from django.urls import reverse

pytestmark = pytest.mark.django_db

URL = reverse("education:index")


def test_anonymous_sees_text_and_film(client):
    response = client.get(URL)

    assert response.status_code == 200
    html = response.content.decode()
    assert "Materiały edukacyjne" in html
    assert "„Drzewo dla Pokoleń”" in html
    assert f'src="{static("video/sadzenie-drzewa.mp4")}"' in html
    assert 'type="video/mp4"' in html


def test_film_does_not_download_before_play(client):
    # The page is open to everyone, often on mobile data; the film is tens of megabytes.
    html = client.get(URL).content.decode()

    assert 'preload="metadata"' in html


@pytest.mark.parametrize("logged_in", [False, True])
def test_nav_links_to_materials(client, user, logged_in):
    if logged_in:
        client.force_login(user)

    html = client.get(reverse("trees:map")).content.decode()

    assert f'href="{URL}"' in html


def test_nav_marks_materials_active(client):
    html = client.get(URL).content.decode()

    assert f'<a href="{URL}" class="active" aria-current="page">Materiały</a>' in html
