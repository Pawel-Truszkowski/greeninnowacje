"""Daily weather fetch (spec §6: 05:00). Joins the HTTP client with the storage layer.

Deliberately exits 0 even when some localities fail: a third-party API being briefly
unreachable is normal, and a cron job that alerts every time teaches everyone to ignore
it. Failures are counted in the summary and logged instead. Recomputing statuses is a
separate job, so both can be run and debugged independently.
"""

import logging

from django.core.management.base import BaseCommand

from trees.models import Locality
from weather.open_meteo import WeatherUnavailable, fetch_daily
from weather.services import store_readings

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Pobiera opady dla miejscowości z Open-Meteo (spec §5.1)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=1, help="Ile zakończonych dni wstecz.")
        parser.add_argument("--locality", type=int, help="Tylko ta miejscowość (diagnostyka).")

    def handle(self, *args, days, locality, **options):
        localities = Locality.objects.all()
        if locality:
            localities = localities.filter(pk=locality)

        stored_total = skipped_total = failed = 0
        for loc in localities:
            try:
                # Today is skipped by store_readings anyway, so we do not fetch it.
                readings = fetch_daily(loc.lat, loc.lng, past_days=days, forecast_days=0)
                result = store_readings(loc, readings)
            except WeatherUnavailable as error:
                failed += 1
                logger.warning("Brak danych pogodowych dla miejscowości %s: %s", loc, error)
                self.stderr.write(f"{loc}: nie udało się pobrać pogody ({error})")
                continue

            stored_total += result.stored
            skipped_total += result.skipped
            self.stdout.write(f"{loc}: zapisano {result.stored}, pominięto {result.skipped}")

        # The summary goes to stdout: it is what a cron log keeps, and the only place
        # anyone will look to tell whether the job is still doing its work.
        summary = (
            f"Gotowe: {len(localities)} miejscowości, zapisano {stored_total} dni, "
            f"pominięto {skipped_total}, nieudanych {failed}."
        )
        self.stdout.write(self.style.WARNING(summary) if failed else self.style.SUCCESS(summary))
