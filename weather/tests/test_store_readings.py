"""Storing Open-Meteo readings in weather_daily (spec §5.1). Written before the code.

Two rules carry most of the weight here:
- only finished days are stored — today's rainfall is still accumulating, and a forecast
  saved as a measurement would quietly understate a drought;
- a reading without rainfall is skipped rather than written as 0 mm, because "no data"
  and "no rain" mean different things to the status algorithm (spec §6.2).
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from factories import LocalityFactory
from weather.models import WeatherDaily
from weather.open_meteo import DailyReading
from weather.services import StoreResult, store_readings

pytestmark = pytest.mark.django_db

TODAY = date(2026, 9, 24)
YESTERDAY = TODAY - timedelta(days=1)
TWO_DAYS_AGO = TODAY - timedelta(days=2)


def reading(day, precip="1.5", temp="18.0"):
    return DailyReading(
        day=day,
        precip_mm=None if precip is None else Decimal(precip),
        temp_max_c=None if temp is None else Decimal(temp),
    )


@pytest.fixture
def locality():
    return LocalityFactory(name="Sierpc")


class TestStoring:
    def test_finished_days_are_stored(self, locality):
        result = store_readings(
            locality,
            [reading(TWO_DAYS_AGO, "0.0"), reading(YESTERDAY, "3.2", "15.4")],
            today=TODAY,
        )

        assert result == StoreResult(stored=2, skipped=0)
        row = WeatherDaily.objects.get(locality=locality, day=YESTERDAY)
        assert row.precip_mm == Decimal("3.20")
        assert row.temp_max_c == Decimal("15.4")
        assert row.source == "open-meteo"

    def test_values_are_rounded_to_the_column_precision(self, locality):
        store_readings(locality, [reading(YESTERDAY, "3.456")], today=TODAY)

        assert WeatherDaily.objects.get().precip_mm == Decimal("3.46")

    def test_reading_without_temperature_is_still_stored(self, locality):
        store_readings(locality, [reading(YESTERDAY, "2.0", None)], today=TODAY)

        row = WeatherDaily.objects.get()
        assert row.precip_mm == Decimal("2.00")
        assert row.temp_max_c is None

    def test_empty_input(self, locality):
        assert store_readings(locality, [], today=TODAY) == StoreResult(0, 0)
        assert not WeatherDaily.objects.exists()


class TestSkipping:
    def test_today_is_not_stored(self, locality):
        """Today's rainfall is still accumulating — it is a forecast, not a measurement."""
        result = store_readings(locality, [reading(TODAY, "0.1")], today=TODAY)

        assert result == StoreResult(stored=0, skipped=1)
        assert not WeatherDaily.objects.exists()

    def test_future_days_are_not_stored(self, locality):
        result = store_readings(locality, [reading(TODAY + timedelta(days=1))], today=TODAY)

        assert result == StoreResult(stored=0, skipped=1)
        assert not WeatherDaily.objects.exists()

    def test_reading_without_rainfall_is_skipped(self, locality):
        """0 mm would claim "it did not rain"; a missing row says "we do not know"."""
        result = store_readings(locality, [reading(YESTERDAY, None, "17.0")], today=TODAY)

        assert result == StoreResult(stored=0, skipped=1)
        assert not WeatherDaily.objects.exists()

    def test_mixed_batch(self, locality):
        result = store_readings(
            locality,
            [
                reading(TWO_DAYS_AGO, "1.0"),
                reading(YESTERDAY, None),
                reading(TODAY, "0.5"),
            ],
            today=TODAY,
        )

        assert result == StoreResult(stored=1, skipped=2)
        assert list(WeatherDaily.objects.values_list("day", flat=True)) == [TWO_DAYS_AGO]


class TestUpsert:
    def test_second_run_updates_instead_of_duplicating(self, locality):
        store_readings(locality, [reading(YESTERDAY, "1.0")], today=TODAY)
        result = store_readings(locality, [reading(YESTERDAY, "4.4", "21.0")], today=TODAY)

        assert result == StoreResult(stored=1, skipped=0)
        row = WeatherDaily.objects.get()
        assert row.precip_mm == Decimal("4.40")
        assert row.temp_max_c == Decimal("21.0")

    def test_replaces_seeded_data(self, locality):
        WeatherDaily.objects.create(
            locality=locality, day=YESTERDAY, precip_mm=Decimal("9.9"), source="seed"
        )

        store_readings(locality, [reading(YESTERDAY, "0.0")], today=TODAY)

        row = WeatherDaily.objects.get()
        assert row.source == "open-meteo"
        assert row.precip_mm == Decimal("0.00")

    def test_other_localities_are_untouched(self, locality):
        other = LocalityFactory(name="Studzieniec")
        WeatherDaily.objects.create(locality=other, day=YESTERDAY, precip_mm=Decimal("7.0"))

        store_readings(locality, [reading(YESTERDAY, "1.0")], today=TODAY)

        assert WeatherDaily.objects.get(locality=other).precip_mm == Decimal("7.00")
        assert WeatherDaily.objects.count() == 2


def test_today_defaults_to_the_current_date(locality):
    """Callers may omit `today`; the cron command has no reason to pass it."""
    yesterday_for_real = date.today() - timedelta(days=1)

    result = store_readings(locality, [reading(yesterday_for_real, "2.0")])

    assert result.stored == 1
