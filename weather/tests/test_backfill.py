"""Backfilling a brand-new locality (spec §5.1).

Without it a tree registered in a new village has no rainfall data until the next 05:00
run, so its card shows a chart full of gaps. With it, the history is there the moment the
volunteer finishes the form.

The rule that matters more than the feature: registering a tree must never depend on
Open-Meteo being up. The volunteer is standing in a field; a third-party outage cannot be
allowed to cost them their work.
"""

import logging
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from core.models import load_drought_config
from factories import LocalityFactory, UserFactory
from trees.models import Locality, Tree
from weather.models import WeatherDaily
from weather.open_meteo import DailyReading, WeatherUnavailable
from weather.services import backfill_locality

pytestmark = pytest.mark.django_db


def readings(days):
    yesterday = timezone.localdate() - timedelta(days=1)
    return [
        DailyReading(yesterday - timedelta(days=offset), Decimal("1.0"), Decimal("15.0"))
        for offset in reversed(range(days))
    ]


@pytest.fixture
def api(monkeypatch):
    calls = []

    def fake_fetch(lat, lng, **kwargs):
        calls.append({"lat": lat, "lng": lng, **kwargs})
        return readings(kwargs.get("past_days", 1))

    monkeypatch.setattr("weather.services.fetch_daily", fake_fetch)
    return calls


@pytest.fixture
def broken_api(monkeypatch):
    def always_down(lat, lng, **kwargs):
        raise WeatherUnavailable("API niedostępne")

    monkeypatch.setattr("weather.services.fetch_daily", always_down)


class TestBackfillLocality:
    def test_fetches_the_whole_drought_window(self, api):
        locality = LocalityFactory(name="Rachocin")
        window = load_drought_config().rain_window_days

        backfill_locality(locality)

        assert api[0]["past_days"] == window
        assert WeatherDaily.objects.filter(locality=locality).count() == window

    def test_does_not_wait_through_the_retry_backoff(self, api):
        """A volunteer is waiting for the form to submit — fail fast instead."""
        backfill_locality(LocalityFactory())

        assert api[0]["retry_delays"] == (0,)

    def test_failure_is_logged_and_swallowed(self, broken_api, caplog):
        locality = LocalityFactory()

        with caplog.at_level(logging.WARNING, logger="weather.services"):
            result = backfill_locality(locality)

        assert result.stored == 0
        assert not WeatherDaily.objects.exists()
        assert locality.name in caplog.text


class TestRegistrationTriggersBackfill:
    @pytest.fixture
    def volunteer(self, client):
        user = UserFactory()
        client.force_login(user)
        return user

    def payload(self, **overrides):
        return {
            "species": "Lipa drobnolistna",
            "planted_on": timezone.localdate().isoformat(),
            "planted_by": "",
            "notes": "",
            "lat": "52.871000",
            "lng": "19.651000",
            "gps_accuracy_m": "4.0",
            "locality_name": "Rachocin",
        } | overrides

    def test_new_locality_gets_its_weather(
        self, client, volunteer, api, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            response = client.post(
                reverse("trees-api:create"), self.payload(), content_type="application/json"
            )

        assert response.status_code == 201
        locality = Locality.objects.get(name="Rachocin")
        assert WeatherDaily.objects.filter(locality=locality).exists()

    def test_existing_locality_is_not_refetched(
        self, client, volunteer, api, django_capture_on_commit_callbacks
    ):
        """Known localities are the cron job's business, not the registration form's."""
        LocalityFactory(name="Rachocin")

        with django_capture_on_commit_callbacks(execute=True):
            client.post(
                reverse("trees-api:create"), self.payload(), content_type="application/json"
            )

        assert api == []

    def test_registration_survives_a_weather_outage(
        self, client, volunteer, broken_api, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            response = client.post(
                reverse("trees-api:create"), self.payload(), content_type="application/json"
            )

        assert response.status_code == 201
        assert Tree.objects.count() == 1
        assert not WeatherDaily.objects.exists()


def test_client_supports_a_single_attempt():
    """The knob the backfill relies on: fetch_daily(retry_delays=(0,)) tries once."""
    import inspect

    from weather.open_meteo import fetch_daily

    assert "retry_delays" in inspect.signature(fetch_daily).parameters
