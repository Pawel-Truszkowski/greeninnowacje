"""Retention: activity is personal data, so it does not live forever (RODO). Written first.

`prune_activity` deletes events older than `--days` (default `ACTIVITY_RETENTION_DAYS`)
and nothing else. Unlike `waterings`, this table is not append-only — deleting from it is
the whole point of the command.
"""

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from activity.models import ActivityEvent

pytestmark = pytest.mark.django_db

Kind = ActivityEvent.Kind


def event(days_ago):
    return ActivityEvent.objects.create(
        kind=Kind.LOGIN_FAILED, created_at=timezone.now() - timedelta(days=days_ago)
    )


def prune(*args):
    out = StringIO()
    call_command("prune_activity", *args, stdout=out)
    return out.getvalue()


def test_deletes_only_what_is_older_than_the_limit():
    old, recent = event(400), event(300)

    prune("--days", "365")

    assert not ActivityEvent.objects.filter(pk=old.pk).exists()
    assert ActivityEvent.objects.filter(pk=recent.pk).exists()


def test_default_comes_from_settings(settings):
    settings.ACTIVITY_RETENTION_DAYS = 30
    old, recent = event(31), event(29)

    prune()

    assert not ActivityEvent.objects.filter(pk=old.pk).exists()
    assert ActivityEvent.objects.filter(pk=recent.pk).exists()


def test_dry_run_deletes_nothing_but_says_how_much_it_would():
    event(400)
    event(401)

    output = prune("--days", "365", "--dry-run")

    assert ActivityEvent.objects.filter(kind=Kind.LOGIN_FAILED).count() == 2
    assert "2" in output


def test_reports_how_many_it_deleted():
    event(400)

    assert "1" in prune("--days", "365")


@pytest.mark.parametrize("days", ["0", "-5"])
def test_refuses_a_limit_that_would_wipe_today(days):
    from django.core.management.base import CommandError

    event(1)

    with pytest.raises(CommandError):
        prune("--days", days)

    assert ActivityEvent.objects.filter(kind=Kind.LOGIN_FAILED).exists()
