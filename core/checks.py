"""Startup configuration checks (manage.py check / runserver / migrate)."""

from django.conf import settings
from django.core.checks import Error, register

TILE_PLACEHOLDERS = ("{z}", "{x}", "{y}")


@register()
def map_tiles_url_is_a_template(app_configs, **kwargs):
    """MAP_TILES_URL must be a tile template, not a link copied from a provider's viewer.

    Without the placeholders Leaflet has nothing to substitute, and the map silently
    renders empty — a mistake that is easy to make and hard to spot in the browser.
    """
    url = settings.MAP_TILES_URL
    missing = [token for token in TILE_PLACEHOLDERS if token not in url]
    if not missing:
        return []
    return [
        Error(
            f"MAP_TILES_URL is missing the tile placeholders: {', '.join(missing)}.",
            hint=(
                "Use a tile template, e.g. "
                "https://api.maptiler.com/maps/streets-v2/{z}/{x}/{y}.png?key=... — "
                "not the viewer link from the provider's dashboard."
            ),
            id="core.E001",
        )
    ]
