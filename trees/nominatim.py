"""Reverse geocoding via Nominatim (spec §5.2).

OSM's usage policy requires an identifying User-Agent and at most one request per
second. We only call this when a volunteer registers a tree, so a simple process-wide
throttle is enough. Any failure is non-fatal: the form then asks for the locality name.
"""

import logging
import threading
import time

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

MIN_INTERVAL_S = 1.0
TIMEOUT_S = 10.0
ADDRESS_KEYS = ("city", "town", "village", "municipality", "hamlet")

_throttle_lock = threading.Lock()
_last_call_at = 0.0


def _wait_for_slot():
    global _last_call_at
    with _throttle_lock:
        wait = MIN_INTERVAL_S - (time.monotonic() - _last_call_at)
        if wait > 0:
            time.sleep(wait)
        _last_call_at = time.monotonic()


def reverse_locality(lat, lng):
    """Return the locality name for the coordinates, or None when it cannot be found."""
    _wait_for_slot()
    params = {
        "lat": str(lat),
        "lon": str(lng),
        "format": "jsonv2",
        "zoom": 13,
        "accept-language": "pl",
    }
    headers = {"User-Agent": settings.NOMINATIM_USER_AGENT}
    try:
        response = httpx.get(
            f"{settings.NOMINATIM_URL.rstrip('/')}/reverse",
            params=params,
            headers=headers,
            timeout=TIMEOUT_S,
        )
        response.raise_for_status()
        address = response.json().get("address", {})
    except (httpx.HTTPError, ValueError) as error:
        logger.warning("Nominatim nie odpowiedział poprawnie: %s", error)
        return None

    for key in ADDRESS_KEYS:
        if address.get(key):
            return address[key]
    logger.info("Nominatim nie zwrócił nazwy miejscowości dla %s, %s", lat, lng)
    return None
