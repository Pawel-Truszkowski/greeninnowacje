"""Storing weather readings (spec §5.1).

Kept apart from `open_meteo.py` on purpose: that module only talks HTTP, this one only
talks to the database, and the cron command joins them. Each can be tested without the
other — no network here, no database there.
"""

import logging
from dataclasses import dataclass

from django.utils import timezone

from .models import WeatherDaily

logger = logging.getLogger(__name__)

SOURCE = "open-meteo"


@dataclass(frozen=True)
class StoreResult:
    stored: int
    skipped: int


def _is_storable(reading, today):
    """A reading worth keeping: a finished day with an actual rainfall figure.

    Today is still accumulating rain, so Open-Meteo's value for it is a forecast; stored
    as a measurement it would understate a drought. A reading without rainfall is left
    out entirely rather than written as 0 mm — the column is NOT NULL, and "no data" must
    not turn into "it did not rain" (spec §6.2).
    """
    return reading.day < today and reading.precip_mm is not None


def store_readings(locality, readings, *, today=None) -> StoreResult:
    """Upsert readings for one locality; returns how many were stored and skipped."""
    today = today or timezone.localdate()
    storable = [reading for reading in readings if _is_storable(reading, today)]
    skipped = len(readings) - len(storable)

    if storable:
        WeatherDaily.objects.bulk_create(
            [
                WeatherDaily(
                    locality=locality,
                    day=reading.day,
                    precip_mm=reading.precip_mm,
                    temp_max_c=reading.temp_max_c,
                    source=SOURCE,
                )
                for reading in storable
            ],
            update_conflicts=True,
            unique_fields=["locality", "day"],
            update_fields=["precip_mm", "temp_max_c", "source"],
        )

    if skipped:
        logger.debug(
            "Pominięto %d odczytów dla miejscowości %s (dzień niezakończony lub brak opadu)",
            skipped,
            locality,
        )
    return StoreResult(stored=len(storable), skipped=skipped)
