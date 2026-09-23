"""Drought status algorithm (spec §6.2).

Pure functions: dates and numbers in, a status out — no database access, so every edge
case from the spec is a one-line test. `recompute_tree_status` in services.py feeds it.

Two notions of "wet" are deliberately different:
- `recently_watered`: watered within DAYS_SOON days → OK regardless of rainfall,
- `last_wet`: the most recent day it either rained (>= RAIN_WET_MM) or was watered;
  the reference point for counting dry days.
"""

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .models import Tree

logger = logging.getLogger(__name__)

# A day counts as wet when it brought at least this much rain (spec §6.2).
RAIN_WET_MM = Decimal("1.0")


@dataclass(frozen=True)
class StatusInputs:
    """Everything the algorithm may look at."""

    today: date
    planted_on: date
    created_on: date
    last_watered_on: date | None
    # Rainfall for the window, newest day last; None = no reading for that day.
    rainfall: list[tuple[date, Decimal | None]]


def rain_total_mm(rainfall):
    """Sum of known readings. Missing days count as 0 mm, but are reported separately."""
    return sum((mm for _, mm in rainfall if mm is not None), Decimal("0"))


def missing_rain_days(rainfall):
    return [day for day, mm in rainfall if mm is None]


def last_rain_day(rainfall):
    wet_days = [day for day, mm in rainfall if mm is not None and mm >= RAIN_WET_MM]
    return max(wet_days) if wet_days else None


def last_watered_day(inputs):
    """Most recent day the tree got water from a person.

    Planting counts: a newly planted tree is always watered thoroughly (rollout guide
    1.A.7, "obficie podlać po posadzeniu"), so `planted_on` is a watering we know about
    even though nobody recorded it in the app. A planting date in the future (a typo, or
    a tree registered ahead of an event) is clamped to today rather than trusted.
    """
    planted_on = min(inputs.planted_on, inputs.today)
    return max(filter(None, [inputs.last_watered_on, planted_on]))


def in_registration_grace(inputs, config):
    """True while a tree is too freshly registered to be called URGENT (spec §6.2).

    Registering an older tree would otherwise raise an alarm the moment it is added: its
    planting date is long past, so it would look neglected on day one and the status
    would read as a bug. For DAYS_SOON days after registration the worst it shows is
    "water soon", which still puts it on the volunteer's list.
    """
    return (inputs.today - inputs.created_on).days < config.days_soon


def compute_status(inputs, config):
    """Return the status a tree should have (spec §6.2)."""
    rain_mm = rain_total_mm(inputs.rainfall)
    watered_on = last_watered_day(inputs)
    recently_watered = (inputs.today - watered_on).days <= config.days_soon

    if rain_mm >= config.rain_threshold_mm or recently_watered:
        return Tree.Status.OK

    last_wet = max(filter(None, [watered_on, last_rain_day(inputs.rainfall)]))
    days_dry = (inputs.today - last_wet).days
    if days_dry >= config.days_urgent and not in_registration_grace(inputs, config):
        return Tree.Status.URGENT
    return Tree.Status.SOON
