from dataclasses import dataclass
from decimal import Decimal

from django.db import models


class Config(models.Model):
    """Drought thresholds as key/value pairs (spec §3, table `config`); editable by admins."""

    key = models.CharField(max_length=64, primary_key=True)
    value = models.CharField(max_length=255)

    class Meta:
        db_table = "config"
        verbose_name = "ustawienie"
        verbose_name_plural = "ustawienia"

    def __str__(self):
        return f"{self.key}={self.value}"


DEFAULTS = {
    "RAIN_WINDOW_DAYS": "5",
    "RAIN_THRESHOLD_MM": "10",
    "DAYS_URGENT": "5",
    "DAYS_SOON": "3",
}


@dataclass(frozen=True)
class DroughtConfig:
    rain_window_days: int
    rain_threshold_mm: Decimal
    days_soon: int
    days_urgent: int


def load_drought_config() -> DroughtConfig:
    values = DEFAULTS | dict(Config.objects.values_list("key", "value"))
    return DroughtConfig(
        rain_window_days=int(values["RAIN_WINDOW_DAYS"]),
        rain_threshold_mm=Decimal(values["RAIN_THRESHOLD_MM"]),
        days_soon=int(values["DAYS_SOON"]),
        days_urgent=int(values["DAYS_URGENT"]),
    )
