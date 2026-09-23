import pytest
from django.core.checks import run_checks

from core.checks import map_tiles_url_is_a_template


@pytest.mark.parametrize(
    "url",
    [
        "https://api.maptiler.com/maps/streets-v2/{z}/{x}/{y}.png?key=abc",
        "https://tile.openstreetmap.de/{z}/{x}/{y}.png",
    ],
)
def test_accepts_tile_templates(settings, url):
    settings.MAP_TILES_URL = url
    assert map_tiles_url_is_a_template(None) == []


def test_rejects_viewer_link(settings):
    """The URL the MapTiler dashboard shows for its map preview — a common mix-up."""
    settings.MAP_TILES_URL = "https://api.maptiler.com/maps/openstreetmap/?key=abc#0.7/22.8/2.8"

    (error,) = map_tiles_url_is_a_template(None)

    assert error.id == "core.E001"
    assert "{z}" in error.msg


def test_check_is_registered(settings):
    settings.MAP_TILES_URL = "https://example.test/tiles.png"
    assert any(error.id == "core.E001" for error in run_checks())
