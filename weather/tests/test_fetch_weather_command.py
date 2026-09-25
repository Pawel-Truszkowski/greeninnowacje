"""`fetch_weather` — the daily cron job (spec §6, 05:00). Written before the code.

The command is the only place where the HTTP client and the database layer meet. Its own
job is small but specific: walk the localities, and make sure one unreachable API call
does not stop the rest — a cron run that gives up halfway would leave some localities
stale without anyone noticing (spec §5.1: "log + kontynuacja").
"""

from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from factories import LocalityFactory
from weather.models import WeatherDaily
from weather.open_meteo import DailyReading, WeatherUnavailable

pytestmark = pytest.mark.django_db


def readings(days=2, end_day=None):
    """Finished days, oldest first — what Open-Meteo returns for past_days=N."""
    end_day = end_day or timezone.localdate() - timedelta(days=1)
    return [
        DailyReading(
            day=end_day - timedelta(days=offset),
            precip_mm=Decimal("1.5"),
            temp_max_c=Decimal("18.0"),
        )
        for offset in reversed(range(days))
    ]


@pytest.fixture
def localities():
    # Distinct coordinates: the failure tests tell the localities apart by latitude.
    return [
        LocalityFactory(name="Sierpc", lat=Decimal("52.871000"), lng=Decimal("19.651000")),
        LocalityFactory(name="Studzieniec", lat=Decimal("52.849000"), lng=Decimal("19.723000")),
    ]


@pytest.fixture
def api(monkeypatch):
    """Records calls and returns readings; no network in tests (spec §9)."""
    calls = []

    def fake_fetch(lat, lng, *, past_days=1, forecast_days=1):
        calls.append({"lat": lat, "lng": lng, "past_days": past_days})
        return readings(days=past_days)

    monkeypatch.setattr("weather.management.commands.fetch_weather.fetch_daily", fake_fetch)
    return calls


def run(*args):
    out = StringIO()
    call_command("fetch_weather", *args, stdout=out, stderr=StringIO())
    return out.getvalue()


class TestHappyPath:
    def test_fetches_every_locality(self, localities, api):
        run()

        assert len(api) == 2
        assert {call["lat"] for call in api} == {loc.lat for loc in localities}

    def test_stores_the_readings(self, localities, api):
        run("--days", "2")

        assert WeatherDaily.objects.count() == 4  # 2 localities × 2 days
        assert set(WeatherDaily.objects.values_list("source", flat=True)) == {"open-meteo"}

    def test_prints_a_summary(self, localities, api):
        """The cron log usually keeps stdout only — the numbers have to be there."""
        output = run("--days", "2")

        assert "Sierpc" in output and "Studzieniec" in output
        assert "2" in output  # stored days

    def test_running_twice_changes_nothing(self, localities, api):
        run()
        before = list(WeatherDaily.objects.values_list("locality", "day", "precip_mm"))

        run()

        assert list(WeatherDaily.objects.values_list("locality", "day", "precip_mm")) == before

    def test_no_localities_is_not_an_error(self, api):
        output = run()

        assert api == []
        assert output.strip()  # says something rather than failing


class TestFailures:
    def test_one_broken_locality_does_not_stop_the_others(self, localities, monkeypatch, caplog):
        def flaky(lat, lng, *, past_days=1, forecast_days=1):
            if lat == localities[0].lat:
                raise WeatherUnavailable("API niedostępne")
            return readings()

        monkeypatch.setattr("weather.management.commands.fetch_weather.fetch_daily", flaky)

        output = run()

        assert WeatherDaily.objects.filter(locality=localities[1]).exists()
        assert not WeatherDaily.objects.filter(locality=localities[0]).exists()
        assert "Sierpc" in caplog.text or "Sierpc" in output

    def test_failure_is_reported_but_the_command_succeeds(self, localities, monkeypatch):
        """Cron must not treat a flaky third-party API as a failed job."""

        def always_down(lat, lng, *, past_days=1, forecast_days=1):
            raise WeatherUnavailable("API niedostępne")

        monkeypatch.setattr("weather.management.commands.fetch_weather.fetch_daily", always_down)

        output = run()  # call_command raises on a non-zero exit

        assert "2" in output  # both localities reported as failed in the summary


class TestOptions:
    def test_days_option_is_passed_to_the_client(self, localities, api):
        run("--days", "5")

        assert {call["past_days"] for call in api} == {5}
        assert WeatherDaily.objects.filter(locality=localities[0]).count() == 5

    def test_locality_option_limits_the_run(self, localities, api):
        run("--locality", str(localities[1].pk))

        assert len(api) == 1
        assert api[0]["lat"] == localities[1].lat

    def test_unfinished_days_are_not_stored(self, localities, monkeypatch):
        """The storage layer filters them; the command must not work around it."""
        today = timezone.localdate()

        def with_today(lat, lng, *, past_days=1, forecast_days=1):
            return [*readings(days=1), DailyReading(today, Decimal("9.9"), None)]

        monkeypatch.setattr("weather.management.commands.fetch_weather.fetch_daily", with_today)

        run()

        assert not WeatherDaily.objects.filter(day=today).exists()


def test_command_does_not_recompute_statuses(localities, api, monkeypatch):
    """Recomputing is a separate cron job (spec §6) — keep the jobs independent."""
    called = []
    monkeypatch.setattr(
        "trees.services.recompute_tree_status", lambda *args, **kwargs: called.append(args)
    )

    run()

    assert called == []


def test_readings_helper_produces_finished_days():
    """Guard for the fixture itself: everything it returns is in the past."""
    assert all(reading.day < date.today() for reading in readings(days=3))
