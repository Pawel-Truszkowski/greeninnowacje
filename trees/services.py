"""Write-side operations on trees (spec §4, volunteer endpoints).

Views — HTML and JSON alike — call these; they own the invariants, so a rule like
"one active caretaker" or "recompute the status right after watering" cannot be
forgotten in one entry point and remembered in another.
"""

import logging

from django.db import IntegrityError, transaction
from django.db.models import BooleanField, Case, F, IntegerField, Max, Value, When
from django.utils import timezone

from core.models import load_drought_config

from .models import Assignment, Tree, Watering
from .selectors import weather_series
from .status import StatusInputs, compute_status, missing_rain_days

logger = logging.getLogger(__name__)


class CaretakerConflict(Exception):
    """Somebody else is already looking after this tree."""


def _status_inputs(tree, today, config):
    window = weather_series(tree.locality_id, days=config.rain_window_days, today=today)
    last_watered_at = tree.waterings.aggregate(last=Max("watered_at"))["last"]
    return StatusInputs(
        today=today,
        planted_on=tree.planted_on,
        created_on=timezone.localtime(tree.created_at).date(),
        last_watered_on=timezone.localtime(last_watered_at).date() if last_watered_at else None,
        rainfall=[(day["day"], day["precip_mm"]) for day in window],
    )


def recompute_tree_status(tree, today=None, save=True):
    """Recompute one tree's status; writes only when it actually changed (spec §6.2)."""
    today = today or timezone.localdate()
    config = load_drought_config()
    inputs = _status_inputs(tree, today, config)

    missing = missing_rain_days(inputs.rainfall)
    if missing:
        # Treated as 0 mm, but a gap means the status may be based on partial data.
        logger.warning(
            "Niepełne dane pogodowe dla miejscowości %s: brakuje %d z %d dni (%s)",
            tree.locality_id,
            len(missing),
            config.rain_window_days,
            ", ".join(day.isoformat() for day in missing),
        )

    status = compute_status(inputs, config)
    if save and status != tree.status:
        tree.status = status
        tree.save(update_fields=["status"])
    return status


@transaction.atomic
def record_watering(tree, user, watered_at=None):
    """Append a watering and refresh the status immediately — no waiting for cron."""
    watering = Watering.objects.create(
        tree=tree, user=user, **({"watered_at": watered_at} if watered_at else {})
    )
    status = recompute_tree_status(tree)
    return watering, status


def assign_caretaker(tree, user):
    """Volunteer takes care of a tree; the DB constraint decides who wins a race."""
    try:
        with transaction.atomic():
            return Assignment.objects.create(tree=tree, user=user)
    except IntegrityError as error:
        raise CaretakerConflict("To drzewo ma już aktywnego opiekuna.") from error


def release_caretaker(tree, user):
    """End this user's own active assignment. Returns True if there was one."""
    updated = Assignment.objects.filter(tree=tree, user=user, ended_at__isnull=True).update(
        ended_at=timezone.now()
    )
    return bool(updated)


def caretaker_of(tree):
    assignment = (
        Assignment.objects.filter(tree=tree, ended_at__isnull=True).select_related("user").first()
    )
    return assignment.user if assignment else None


def my_trees(user):
    """Trees the user looks after: most urgent first, then longest unwatered (spec §4)."""
    status_rank = Case(
        When(status=Tree.Status.URGENT, then=Value(0)),
        When(status=Tree.Status.SOON, then=Value(1)),
        default=Value(2),
        output_field=IntegerField(),
    )
    return (
        Tree.objects.filter(
            assignments__user=user,
            assignments__ended_at__isnull=True,
            lifecycle=Tree.Lifecycle.ACTIVE,
        )
        .select_related("locality")
        .annotate(
            status_rank=status_rank,
            last_watered_at=Max("waterings__watered_at"),
            # By definition every tree in this list has an active caretaker: the user.
            has_caretaker=Value(True, output_field=BooleanField()),
        )
        # PostgreSQL sorts NULLs last on ASC, but "never watered" is the most urgent
        # case within a status, so it has to come first.
        .order_by("status_rank", F("last_watered_at").asc(nulls_first=True))
    )


def days_since(moment, today=None):
    if moment is None:
        return None
    today = today or timezone.localdate()
    return (today - timezone.localtime(moment).date()).days


def watering_history(tree, limit=None):
    """Full history with authors — for logged-in users only (spec §4)."""
    query = tree.waterings.select_related("user").order_by("-watered_at")
    return query[:limit] if limit else query


def humanized_days(days):
    """'dziś' / 'wczoraj' / 'N dni temu' for the UI."""
    if days is None:
        return None
    if days <= 0:
        return "dziś"
    if days == 1:
        return "wczoraj"
    return f"{days} dni temu"
