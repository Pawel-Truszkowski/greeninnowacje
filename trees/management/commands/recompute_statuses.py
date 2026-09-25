"""Daily status recompute (spec §6: 07:00, after the weather has been fetched).

Separate from fetch_weather on purpose: when the weather API is down we still want the
statuses recomputed from whatever data we have, and each job can be rerun on its own.
"""

from django.core.management.base import BaseCommand

from trees.services import recompute_all


class Command(BaseCommand):
    help = "Przelicza statusy suszy dla aktywnych drzew (spec §6.2)."

    def add_arguments(self, parser):
        parser.add_argument("--locality", type=int, help="Tylko ta miejscowość.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Pokaż, co by się zmieniło, bez zapisu (kalibracja progów).",
        )

    def handle(self, *args, locality, dry_run, **options):
        result = recompute_all(locality_id=locality, save=not dry_run)

        breakdown = ", ".join(
            f"{status}: {count}" for status, count in sorted(result.counts.items())
        )
        summary = (
            f"{'[próba] ' if dry_run else ''}Sprawdzono {result.checked} drzew, "
            f"zmieniono {result.changed}. Statusy — {breakdown or 'brak drzew'}."
        )
        self.stdout.write(self.style.SUCCESS(summary))
