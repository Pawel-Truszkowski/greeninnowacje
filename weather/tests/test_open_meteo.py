"""Open-Meteo client (spec §5.1). Written before the implementation.

The client only talks HTTP and parses: no database writes, no swallowed errors. When the
API cannot be reached it raises, and the cron command decides what to do — log the gap
and carry on — because a missing reading is not 0 mm of rain (spec §6.2).
"""

from datetime import date
from decimal import Decimal

import httpx
import pytest
import respx

from weather.open_meteo import RETRY_DELAYS, DailyReading, WeatherUnavailable, fetch_daily

API = "https://api.open-meteo.com/v1/forecast"
SIERPC = (52.871, 19.651)


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    """Retries must not slow the suite down; record the delays instead."""
    slept = []
    monkeypatch.setattr("weather.open_meteo.time.sleep", slept.append)
    return slept


def route():
    return respx.get(url__startswith=API)


def payload(days=("2026-09-23", "2026-09-24"), precip=(3.2, 0.0), temps=(18.1, 20.4)):
    return {
        "daily": {
            "time": list(days),
            "precipitation_sum": list(precip),
            "temperature_2m_max": list(temps),
        }
    }


class TestRequest:
    @respx.mock
    def test_sends_the_parameters_from_the_spec(self):
        mocked = route().mock(return_value=httpx.Response(200, json=payload()))

        fetch_daily(*SIERPC)

        params = mocked.calls.last.request.url.params
        assert params["latitude"] == "52.871"
        assert params["longitude"] == "19.651"
        assert params["daily"] == "precipitation_sum,temperature_2m_max"
        assert params["past_days"] == "1"
        assert params["forecast_days"] == "1"
        assert params["timezone"] == "Europe/Warsaw"

    @respx.mock
    def test_window_is_configurable(self):
        """Backfilling a new locality needs more than yesterday (spec §5.1)."""
        mocked = route().mock(return_value=httpx.Response(200, json=payload()))

        fetch_daily(*SIERPC, past_days=5, forecast_days=0)

        params = mocked.calls.last.request.url.params
        assert params["past_days"] == "5"
        assert params["forecast_days"] == "0"

    @respx.mock
    def test_uses_a_ten_second_timeout(self):
        mocked = route().mock(return_value=httpx.Response(200, json=payload()))

        fetch_daily(*SIERPC)

        assert mocked.calls.last.request.extensions["timeout"]["connect"] == 10.0


class TestParsing:
    @respx.mock
    def test_returns_readings_in_order(self):
        route().mock(return_value=httpx.Response(200, json=payload()))

        readings = fetch_daily(*SIERPC)

        assert readings == [
            DailyReading(date(2026, 9, 23), Decimal("3.2"), Decimal("18.1")),
            DailyReading(date(2026, 9, 24), Decimal("0.0"), Decimal("20.4")),
        ]

    @respx.mock
    def test_values_are_decimals_without_float_noise(self):
        route().mock(return_value=httpx.Response(200, json=payload(precip=(0.1, 0.2))))

        readings = fetch_daily(*SIERPC)

        assert readings[0].precip_mm == Decimal("0.1")
        assert str(readings[1].precip_mm) == "0.2"

    @respx.mock
    def test_missing_values_stay_none(self):
        """A gap in the data is not zero rain — the status algorithm depends on this."""
        route().mock(return_value=httpx.Response(200, json=payload(precip=(None, 1.0))))

        readings = fetch_daily(*SIERPC)

        assert readings[0].precip_mm is None
        assert readings[1].precip_mm == Decimal("1.0")

    @respx.mock
    def test_missing_temperature_is_tolerated(self):
        route().mock(return_value=httpx.Response(200, json=payload(temps=(None, None))))

        assert [reading.temp_max_c for reading in fetch_daily(*SIERPC)] == [None, None]

    @respx.mock
    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"daily": {}},
            {"daily": {"time": ["2026-09-23"], "precipitation_sum": [1.0, 2.0]}},
            {"error": True, "reason": "Invalid coordinates"},
        ],
        ids=["empty", "no-series", "length-mismatch", "api-error"],
    )
    def test_malformed_response(self, body):
        route().mock(return_value=httpx.Response(200, json=body))

        with pytest.raises(WeatherUnavailable):
            fetch_daily(*SIERPC)

    @respx.mock
    def test_response_that_is_not_json(self):
        route().mock(return_value=httpx.Response(200, text="<html>maintenance</html>"))

        with pytest.raises(WeatherUnavailable):
            fetch_daily(*SIERPC)


class TestRetries:
    @respx.mock
    def test_server_error_is_retried_three_times(self, no_waiting):
        mocked = route().mock(return_value=httpx.Response(500))

        with pytest.raises(WeatherUnavailable):
            fetch_daily(*SIERPC)

        assert mocked.call_count == 3
        assert no_waiting == list(RETRY_DELAYS[:2])  # no sleep after the last attempt

    @respx.mock
    def test_recovers_on_the_second_attempt(self):
        mocked = route().mock(
            side_effect=[httpx.Response(503), httpx.Response(200, json=payload())]
        )

        readings = fetch_daily(*SIERPC)

        assert mocked.call_count == 2
        assert readings[0].day == date(2026, 9, 23)

    @respx.mock
    def test_connection_errors_are_retried(self):
        mocked = route().mock(side_effect=httpx.ConnectError("brak sieci"))

        with pytest.raises(WeatherUnavailable):
            fetch_daily(*SIERPC)

        assert mocked.call_count == 3

    @respx.mock
    def test_timeouts_are_retried(self):
        mocked = route().mock(side_effect=httpx.ReadTimeout("za wolno"))

        with pytest.raises(WeatherUnavailable):
            fetch_daily(*SIERPC)

        assert mocked.call_count == 3

    @respx.mock
    def test_client_errors_are_not_retried(self, no_waiting):
        """4xx means our request is wrong; repeating it cannot help."""
        mocked = route().mock(return_value=httpx.Response(400))

        with pytest.raises(WeatherUnavailable):
            fetch_daily(*SIERPC)

        assert mocked.call_count == 1
        assert no_waiting == []

    @respx.mock
    def test_failure_keeps_the_original_cause(self):
        route().mock(return_value=httpx.Response(500))

        with pytest.raises(WeatherUnavailable) as error:
            fetch_daily(*SIERPC)

        assert error.value.__cause__ is not None


@respx.mock
def test_honours_the_configured_url(settings):
    settings.OPEN_METEO_URL = "https://pogoda.test/v1/forecast"
    mocked = respx.get(url__startswith="https://pogoda.test/v1/forecast").mock(
        return_value=httpx.Response(200, json=payload())
    )

    fetch_daily(*SIERPC)

    assert mocked.called
