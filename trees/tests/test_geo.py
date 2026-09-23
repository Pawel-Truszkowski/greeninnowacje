"""Distance maths behind duplicate detection (spec §4)."""

import pytest

from trees.geo import DUPLICATE_RADIUS_M, bbox_around, haversine_m, is_in_poland

SIERPC = (52.8710, 19.6510)


class TestHaversine:
    def test_same_point_is_zero(self):
        assert haversine_m(*SIERPC, *SIERPC) == 0

    def test_one_degree_of_latitude(self):
        assert haversine_m(52.0, 19.0, 53.0, 19.0) == pytest.approx(111_195, rel=0.001)

    def test_longitude_degrees_are_shorter_this_far_north(self):
        """At 52°N a degree of longitude is ~68 km, not ~111 km — hence the cos(lat)."""
        assert haversine_m(52.0, 19.0, 52.0, 20.0) == pytest.approx(68_500, rel=0.01)

    def test_two_metres_apart(self):
        # ~0.000018° of latitude is about 2 m.
        assert haversine_m(52.871, 19.651, 52.871018, 19.651) == pytest.approx(2.0, abs=0.1)

    def test_accepts_strings_and_decimals(self):
        from decimal import Decimal

        assert haversine_m(Decimal("52.871"), "19.651", 52.871, 19.651) == pytest.approx(0)


class TestBbox:
    def test_contains_points_within_the_radius(self):
        box = bbox_around(*SIERPC, DUPLICATE_RADIUS_M)
        lat, lng = SIERPC

        assert box["min_lat"] < lat < box["max_lat"]
        assert box["min_lng"] < lng < box["max_lng"]

    def test_is_wider_in_longitude_than_in_latitude(self):
        """Longitude degrees are shorter here, so the box must span more of them."""
        box = bbox_around(*SIERPC, 100)

        lat_span = box["max_lat"] - box["min_lat"]
        lng_span = box["max_lng"] - box["min_lng"]

        assert lng_span > lat_span

    def test_covers_a_point_at_the_edge_of_the_radius(self):
        box = bbox_around(*SIERPC, DUPLICATE_RADIUS_M)
        edge_lat = SIERPC[0] + 0.000017  # ~1.9 m north

        assert box["min_lat"] <= edge_lat <= box["max_lat"]


@pytest.mark.parametrize(
    ("lat", "lng", "expected"),
    [
        (52.871, 19.651, True),  # Sierpc
        (54.35, 18.65, True),  # Gdańsk
        (49.3, 19.95, True),  # Tatry
        (48.85, 2.35, False),  # Paryż
        (52.52, 13.40, False),  # Berlin
        (0, 0, False),  # Zatoka Gwinejska — typowy efekt zerowych współrzędnych
    ],
)
def test_is_in_poland(lat, lng, expected):
    assert is_in_poland(lat, lng) is expected
