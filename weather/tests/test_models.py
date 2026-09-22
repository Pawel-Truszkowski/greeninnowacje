from datetime import date
from decimal import Decimal

import pytest

from weather.models import WeatherDaily

pytestmark = pytest.mark.django_db


def upsert(locality, day, mm):
    WeatherDaily.objects.bulk_create(
        [WeatherDaily(locality=locality, day=day, precip_mm=mm)],
        update_conflicts=True,
        unique_fields=["locality", "day"],
        update_fields=["precip_mm"],
    )


def test_upsert_overwrites_same_day(locality):
    upsert(locality, date(2026, 9, 21), Decimal("1.5"))
    upsert(locality, date(2026, 9, 21), Decimal("4.0"))
    row = WeatherDaily.objects.get(locality=locality)
    assert row.precip_mm == Decimal("4.00")
