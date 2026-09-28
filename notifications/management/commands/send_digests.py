"""Daily digest e-mails (spec §6: 07:30, after the statuses have been recomputed at 07:00).

Thin on purpose — the decisions live in `notifications/services.py`, so the same logic is
exercised by the tests and by the cron job.
"""

from datetime import date

from django.core.management.base import BaseCommand

from notifications.services import send_digests


class Command(BaseCommand):
    help = "Wysyła dzienne e-maile o drzewach wymagających podlania (spec §5.3)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--today",
            type=date.fromisoformat,
            help="Zamiast dzisiejszej daty użyj tej (YYYY-MM-DD) — do kalibracji.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Pokaż, ile e-maili poszłoby, bez wysyłki i bez zapisu do email_log.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Zignoruj limit 1 e-mail na dzień (do testów przed demem).",
        )

    def handle(self, *args, today, dry_run, force, **options):
        result = send_digests(today=today, dry_run=dry_run, force=force)

        summary = (
            f"{'[próba] ' if dry_run else ''}Wysłano {result.sent}, "
            f"pominięto {result.skipped} (limit dzienny), błędów {result.failed}."
        )
        style = self.style.WARNING if result.failed else self.style.SUCCESS
        self.stdout.write(style(summary))
