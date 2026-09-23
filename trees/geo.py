"""Distance maths for duplicate detection (spec §4, §9) — no PostGIS needed.

At this scale a bounding-box prefilter in SQL plus an exact distance in Python is both
simpler and fast enough: the box uses the indexed lat/lng columns and leaves at most a
handful of candidates.
"""

import math

EARTH_RADIUS_M = 6_371_008.8
DUPLICATE_RADIUS_M = 2.0

# Poland with a margin; coordinates outside are a client bug, not a tree (spec §7).
POLAND_BOUNDS = {"min_lat": 48.9, "max_lat": 55.1, "min_lng": 13.9, "max_lng": 24.4}


def haversine_m(lat1, lng1, lat2, lng2):
    """Great-circle distance in metres between two WGS84 points."""
    phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
    d_phi = phi2 - phi1
    d_lambda = math.radians(float(lng2) - float(lng1))
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bbox_around(lat, lng, radius_m):
    """Latitude/longitude window that certainly contains everything within `radius_m`.

    Longitude degrees shrink towards the poles, hence the cos(lat) correction; the box is
    deliberately generous, since the exact check happens afterwards.
    """
    lat = float(lat)
    lat_delta = math.degrees(radius_m / EARTH_RADIUS_M)
    lng_delta = lat_delta / max(math.cos(math.radians(lat)), 0.01)
    return {
        "min_lat": lat - lat_delta,
        "max_lat": lat + lat_delta,
        "min_lng": float(lng) - lng_delta,
        "max_lng": float(lng) + lng_delta,
    }


def is_in_poland(lat, lng):
    return (
        POLAND_BOUNDS["min_lat"] <= float(lat) <= POLAND_BOUNDS["max_lat"]
        and POLAND_BOUNDS["min_lng"] <= float(lng) <= POLAND_BOUNDS["max_lng"]
    )
