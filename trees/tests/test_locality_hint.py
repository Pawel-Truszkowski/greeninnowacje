"""The locality hint shown under the map while registering a tree (PoC §8.5).

Two properties matter more than the happy path. It never holds a worker: when the OSM
one-per-second window is busy the endpoint makes no request at all. And no name is a normal
answer — the hint is not a decision, the locality is still resolved when the tree is saved,
so a geocoder that is down must not look like a failure.

Nothing here touches the real Nominatim (spec §9).
"""

import httpx
import pytest
import respx
from django.urls import reverse

from factories import UserFactory

pytestmark = pytest.mark.django_db

URL = reverse("trees-api:locality-hint")
SIERPC = {"lat": "52.871000", "lng": "19.651000"}
NOMINATIM = "https://nominatim.openstreetmap.org/reverse"


@pytest.fixture(autouse=True)
def free_slot(monkeypatch):
    """A free rate window by default; the busy case is one explicit test."""
    monkeypatch.setattr("trees.nominatim._wait_for_slot", lambda wait=True: True)


@pytest.fixture
def volunteer(client):
    client.force_login(UserFactory())
    return client


def geocoder(**address):
    return respx.get(url__startswith=NOMINATIM).mock(
        return_value=httpx.Response(200, json={"address": address})
    )


class TestAnswers:
    @respx.mock
    def test_returns_the_name(self, volunteer):
        geocoder(town="Sierpc")

        response = volunteer.get(URL, SIERPC)

        assert response.status_code == 200
        assert response.json() == {"locality": "Sierpc"}

    @respx.mock
    def test_unknown_place_is_null_not_an_error(self, volunteer):
        geocoder(country="Polska")

        response = volunteer.get(URL, SIERPC)

        assert response.status_code == 200
        assert response.json() == {"locality": None}

    @respx.mock
    def test_geocoder_down_is_null_not_500(self, volunteer):
        """A hint that fails must stay a hint, not an outage on the registration screen."""
        respx.get(url__startswith=NOMINATIM).mock(return_value=httpx.Response(503))

        response = volunteer.get(URL, SIERPC)

        assert response.status_code == 200
        assert response.json() == {"locality": None}

    @respx.mock
    def test_timeout_is_null_too(self, volunteer):
        respx.get(url__startswith=NOMINATIM).mock(side_effect=httpx.ConnectTimeout("zbyt wolno"))

        assert volunteer.get(URL, SIERPC).json() == {"locality": None}


class TestNeverBlocks:
    @respx.mock
    def test_busy_slot_makes_no_http_call(self, volunteer, monkeypatch):
        """The whole point: with the window busy we answer immediately and call nobody.

        Without this, `wait=False` could quietly go back to sleeping for a second and hold
        one of the two gunicorn workers on every keystroke of map dragging.
        """
        monkeypatch.setattr("trees.nominatim._wait_for_slot", lambda wait=True: bool(wait))
        route = geocoder(town="Sierpc")

        response = volunteer.get(URL, SIERPC)

        assert response.json() == {"locality": None}
        assert route.call_count == 0, "Zajęty slot nie może wysłać zapytania"

    def test_registration_still_waits(self, monkeypatch):
        """`register_tree` keeps the blocking behaviour — there the name is needed for real."""
        seen = []
        monkeypatch.setattr("trees.nominatim._wait_for_slot", lambda wait=True: seen.append(wait))

        from trees.nominatim import reverse_locality

        with respx.mock:
            respx.get(url__startswith=NOMINATIM).mock(
                return_value=httpx.Response(200, json={"address": {"town": "Sierpc"}})
            )
            reverse_locality(52.871, 19.651)

        assert seen == [True]


class TestRejects:
    @pytest.mark.parametrize(
        "params",
        [{}, {"lat": "52.871"}, {"lng": "19.651"}, {"lat": "abc", "lng": "19.651"}],
        ids=["brak", "sam lat", "sam lng", "nie liczba"],
    )
    def test_bad_parameters(self, volunteer, params):
        assert volunteer.get(URL, params).status_code == 400

    def test_coordinates_outside_poland(self, volunteer):
        """The same guard the form uses — a hint for Berlin would only mislead."""
        assert volunteer.get(URL, {"lat": "52.5200", "lng": "13.4050"}).status_code == 400

    def test_anonymous_is_forbidden(self, client):
        assert client.get(URL, SIERPC).status_code == 403

    @respx.mock
    def test_rate_limited(self, volunteer, settings):
        """Also proves `methods=("GET",)` is really set: the default would never count."""
        settings.GEOCODE_RATE_LIMIT = "1/h"
        geocoder(town="Sierpc")

        first = volunteer.get(URL, SIERPC)
        second = volunteer.get(URL, SIERPC)

        assert first.status_code == 200
        assert second.status_code == 429
