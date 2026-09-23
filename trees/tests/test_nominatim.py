"""Reverse geocoding client (spec §5.2): identifies itself, fails softly."""

import httpx
import pytest
import respx

from trees.nominatim import reverse_locality


@pytest.fixture(autouse=True)
def no_throttle(monkeypatch):
    monkeypatch.setattr("trees.nominatim._wait_for_slot", lambda: None)


def address(**fields):
    return {"address": fields}


@respx.mock
def test_returns_locality_name():
    route = respx.get(url__startswith="https://nominatim.openstreetmap.org/reverse").mock(
        return_value=httpx.Response(200, json=address(town="Sierpc", county="sierpecki"))
    )

    assert reverse_locality(52.871, 19.651) == "Sierpc"
    request = route.calls.last.request
    assert "GreenInnowacje" in request.headers["User-Agent"]
    assert request.url.params["format"] == "jsonv2"


@respx.mock
@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (address(city="Płock"), "Płock"),
        (address(village="Studzieniec"), "Studzieniec"),
        (address(municipality="Gmina Sierpc"), "Gmina Sierpc"),
        (address(country="Polska"), None),
        ({}, None),
    ],
)
def test_picks_the_most_specific_place(payload, expected):
    respx.get(url__startswith="https://nominatim.openstreetmap.org/reverse").mock(
        return_value=httpx.Response(200, json=payload)
    )

    assert reverse_locality(52.871, 19.651) == expected


@respx.mock
@pytest.mark.parametrize(
    "failure",
    [
        httpx.Response(500),
        httpx.Response(200, text="to nie jest json"),
        httpx.ConnectError("brak sieci"),
    ],
)
def test_failures_are_not_fatal(failure):
    """The form then asks for the locality by hand instead of failing the registration."""
    mock = respx.get(url__startswith="https://nominatim.openstreetmap.org/reverse")
    if isinstance(failure, Exception):
        mock.mock(side_effect=failure)
    else:
        mock.mock(return_value=failure)

    assert reverse_locality(52.871, 19.651) is None
