"""Delete activity events past the retention period (RODO). Runs nightly from deploy/crontab."""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from activity.models import ActivityEvent


class Command(BaseCommand):
    help = "Usuwa zdarzenia aktywności starsze niż okres przechowywania (RODO)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            help="Ile dni przechowywać (domyślnie ACTIVITY_RETENTION_DAYS z ustawień).",
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Tylko policz, niczego nie usuwaj."
        )

    def handle(self, *args, days, dry_run, **options):
        days = settings.ACTIVITY_RETENTION_DAYS if days is None else days
        if days < 1:
            raise CommandError("Okres przechowywania musi wynosić co najmniej 1 dzień.")

        old = ActivityEvent.objects.filter(created_at__lt=timezone.now() - timedelta(days=days))
        if dry_run:
            self.stdout.write(
                f"[próba] Do usunięcia: {old.count()} zdarzeń starszych niż {days} dni."
            )
            return
        deleted, _ = old.delete()
        self.stdout.write(f"Usunięto {deleted} zdarzeń starszych niż {days} dni.")
