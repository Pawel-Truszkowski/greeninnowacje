"""The schedule as a checked artefact (spec §6). Written before the implementation.

A crontab is the classic place for silent rot: rename a management command and the job
keeps "running" every morning, failing into a log nobody reads. These tests tie the
schedule to the code — if a command disappears, the suite says so.
"""

import re
from pathlib import Path

import pytest
from django.core.management import get_commands

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CRONTAB = BASE_DIR / "deploy" / "crontab"
COMPOSE = BASE_DIR / "docker-compose.yml"

# minute hour day month weekday  <command...>
ENTRY = re.compile(r"^(?P<minute>\S+)\s+(?P<hour>\S+)\s+\S+\s+\S+\s+\S+\s+(?P<command>.+)$")


def entries():
    lines = [
        line.strip()
        for line in CRONTAB.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    parsed = []
    for line in lines:
        match = ENTRY.match(line)
        assert match, f"Nie rozpoznano wpisu crontaba: {line!r}"
        parsed.append(match.groupdict())
    return parsed


def django_command(entry):
    """The manage.py command name in a cron entry, or None if it is something else."""
    parts = entry["command"].split()
    if "manage.py" not in parts:
        return None
    return parts[parts.index("manage.py") + 1]


def test_crontab_exists():
    assert CRONTAB.exists(), "Brak pliku deploy/crontab"


def test_every_scheduled_command_exists_in_django():
    """The guard that matters: a renamed command must not slip past unnoticed."""
    known = set(get_commands())

    scheduled = {django_command(entry) for entry in entries()} - {None}

    assert scheduled, "Harmonogram nie uruchamia żadnej komendy Django"
    assert scheduled <= known, f"Nieznane komendy w crontabie: {scheduled - known}"


@pytest.mark.parametrize(
    ("command", "hour"),
    [("fetch_weather", "5"), ("recompute_statuses", "7")],
)
def test_schedule_matches_the_spec(command, hour):
    """Spec §6: weather at 05:00, statuses at 07:00 (Europe/Warsaw)."""
    matching = [entry for entry in entries() if django_command(entry) == command]

    assert len(matching) == 1, f"Oczekiwano jednego wpisu dla {command}"
    assert matching[0]["hour"] == hour
    assert matching[0]["minute"] == "0"


def test_schedule_does_not_touch_the_schema():
    """Migrations belong to the app's startup, not to a job that runs unattended."""
    forbidden = {"migrate", "flush", "seed_demo", "createsuperuser"}

    scheduled = {django_command(entry) for entry in entries()}

    assert not scheduled & forbidden


def test_compose_runs_the_schedule_in_warsaw_time():
    """Cron times are local times; without TZ the container would run on UTC."""
    compose = COMPOSE.read_text(encoding="utf-8")

    assert "supercronic" in compose, "Brak usługi uruchamiającej harmonogram"
    assert "Europe/Warsaw" in compose or "TZ" in compose
