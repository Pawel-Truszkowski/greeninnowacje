import logging
import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

TIMEOUT_S = 10.0
RETRY_DELAYS = (1, 2, 4)


@dataclass(frozen=True)
class DailyReading:
    day: date
    precip_mm: Decimal | None
    temp_max_c: Decimal | None


class WeatherUnavailable(Exception):
    """Raised when the weather service is unreachable or returns an error."""


def fetch_daily(lat, lng, *, past_days=1, forecast_days=1) -> list[DailyReading]:
    """Fetch daily weather readings (rainfall and max temperature) for the given coordinates.

    Returns a list of DailyReading objects, sorted by day ascending. The list includes
    past readings (up to `past_days`) and future forecasts (up to `forecast_days`).
    """
    params = {
        "latitude": str(lat),
        "longitude": str(lng),
        "daily": "precipitation_sum,temperature_2m_max",
        "timezone": "Europe/Warsaw",
        "past_days": str(past_days),
        "forecast_days": str(forecast_days),
    }

    last_error = None
    for attempt, delay in enumerate(RETRY_DELAYS):
        try:
            response = httpx.get(settings.OPEN_METEO_URL, params=params, timeout=TIMEOUT_S)
            response.raise_for_status()
            data = response.json()
            break
        except httpx.HTTPStatusError as error:
            # 4xx means our request is wrong; repeating it cannot help.
            if error.response.status_code < 500:
                logger.warning("Open-Meteo rejected the request: %s", error)
                raise WeatherUnavailable("Open-Meteo rejected the request") from error
            last_error = error
        except (httpx.HTTPError, ValueError) as error:
            last_error = error

        # Reached only after a handled error — a successful attempt leaves via break.
        logger.warning("Open-Meteo request failed: %s", last_error)
        if attempt < len(RETRY_DELAYS) - 1:
            time.sleep(delay)
    else:
        raise WeatherUnavailable("Open-Meteo is unreachable after retries") from last_error

    readings = []

    try:
        for day_str, precip, temp_max in zip(
            data["daily"]["time"],
            data["daily"]["precipitation_sum"],
            data["daily"]["temperature_2m_max"],
            strict=True,
        ):
            readings.append(
                DailyReading(
                    day=date.fromisoformat(day_str),
                    precip_mm=Decimal(str(precip)) if precip is not None else None,
                    temp_max_c=Decimal(str(temp_max)) if temp_max is not None else None,
                )
            )
    except (KeyError, TypeError, ValueError) as error:
        logger.warning("Open-Meteo returned unexpected data: %s", error)
        raise WeatherUnavailable("Open-Meteo returned unexpected data") from error
    return readings
