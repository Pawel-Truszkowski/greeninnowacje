from django.db import models


class WeatherDaily(models.Model):
    """Daily precipitation per locality. A missing row ≠ 0 mm (spec §5.1, §6.2)."""

    locality = models.ForeignKey(
        "trees.Locality", on_delete=models.PROTECT, related_name="weather_days"
    )
    day = models.DateField()
    precip_mm = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    temp_max_c = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    source = models.CharField(max_length=32, default="open-meteo")

    class Meta:
        db_table = "weather_daily"
        verbose_name = "pogoda dzienna"
        verbose_name_plural = "pogoda dzienna"
        ordering = ["locality", "-day"]
        constraints = [
            models.UniqueConstraint(fields=["locality", "day"], name="weather_locality_day_unique"),
        ]

    def __str__(self):
        return f"{self.locality} {self.day}: {self.precip_mm} mm"
