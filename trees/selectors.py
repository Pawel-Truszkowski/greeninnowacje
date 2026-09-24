"""Read-side queries for the public map and the public tree card (spec §4).

`public_tree_card` defines, in one place, exactly what an anonymous visitor may see:
watering history as **dates only**, the caretaker as a yes/no flag, never a person.
Both the HTML card and GET /api/trees/{id}/public render its output.
"""

from datetime import timedelta

from django.db.models import BooleanField, Exists, Max, OuterRef, Value
from django.utils import timezone

from core.models import load_drought_config
from weather.models import WeatherDaily

from .models import Assignment, Tree, TreeSpecies, Watering
from .status_display import STATUS_DISPLAY

WEATHER_CHART_DAYS = 14
PUBLIC_HISTORY_LIMIT = 30


def _active_assignment(tree_ref=None):
    return Assignment.objects.filter(tree=tree_ref or OuterRef("pk"), ended_at__isnull=True)


def map_trees(*, status=None, locality_id=None, bbox=None, user=None):
    """Active trees for the map, with the two extras the popup needs."""
    trees = (
        Tree.objects.filter(lifecycle=Tree.Lifecycle.ACTIVE)
        .annotate(
            last_watered_at=Max("waterings__watered_at"),
            has_caretaker=Exists(_active_assignment()),
        )
        .order_by("planted_on")
    )
    if user:
        trees = trees.annotate(is_mine=Exists(_active_assignment().filter(user=user)))
    else:
        trees = trees.annotate(is_mine=Value(False, output_field=BooleanField()))

    if status:
        trees = trees.filter(status=status)
    if locality_id:
        trees = trees.filter(locality_id=locality_id)
    if bbox:
        west, south, east, north = bbox
        trees = trees.filter(lat__gte=south, lat__lte=north, lng__gte=west, lng__lte=east)
    return trees


def map_tree_payload(tree):
    last_watered_at = tree.last_watered_at
    return {
        "id": str(tree.pk),
        "lat": float(tree.lat),
        "lng": float(tree.lng),
        "species": tree.species,
        "status": tree.status,
        "locality_id": tree.locality_id,
        "last_watered_on": timezone.localtime(last_watered_at).date() if last_watered_at else None,
        "has_caretaker": tree.has_caretaker,
        "is_mine": bool(getattr(tree, "is_mine", False)),
    }


def weather_series(locality_id, days=WEATHER_CHART_DAYS, today=None):
    """Last `days` days of rainfall. A day with no reading is None — not 0 mm (spec §5.1)."""
    today = today or timezone.localdate()
    first_day = today - timedelta(days=days - 1)
    readings = dict(
        WeatherDaily.objects.filter(locality_id=locality_id, day__gte=first_day, day__lte=today)
        .values_list("day", "precip_mm")
    )  # fmt: skip
    return [
        {"day": day, "precip_mm": readings.get(day)}
        for day in (first_day + timedelta(days=offset) for offset in range(days))
    ]


def public_tree_card(tree, today=None):
    today = today or timezone.localdate()
    config = load_drought_config()
    series = weather_series(tree.locality_id, today=today)
    window = series[-config.rain_window_days :] if config.rain_window_days else []

    watering_dates = [
        timezone.localtime(watered_at).date()
        for watered_at in Watering.objects.filter(tree=tree)
        .order_by("-watered_at")
        .values_list("watered_at", flat=True)[:PUBLIC_HISTORY_LIMIT]
    ]

    return {
        "id": str(tree.pk),
        "species": tree.species,
        "planted_on": tree.planted_on,
        "planted_by": tree.planted_by,
        "notes": tree.notes,
        "status": tree.status,
        "status_label": STATUS_DISPLAY[tree.status]["label"],
        "status_hint": STATUS_DISPLAY[tree.status]["hint"],
        "lifecycle": tree.lifecycle,
        "lat": float(tree.lat),
        "lng": float(tree.lng),
        "locality": {"id": tree.locality_id, "name": tree.locality.name},
        # Dates only, never the volunteers who did the watering (spec §4).
        "waterings": watering_dates,
        "waterings_total": Watering.objects.filter(tree=tree).count(),
        "has_caretaker": _active_assignment(tree).exists(),
        "weather": series,
        "rain_window_days": config.rain_window_days,
        "rain_threshold_mm": float(config.rain_threshold_mm),
        "rain_window_mm": float(sum(day["precip_mm"] or 0 for day in window)),
        "weather_missing_days": sum(1 for day in window if day["precip_mm"] is None),
    }


def extended_tree_card(tree, today=None):
    """Card for logged-in users: the public card plus who watered and who cares for it.

    This is the only place where volunteer names join tree data; the public card
    (`public_tree_card`) must never gain these keys.
    """
    from .services import caretaker_of, watering_history

    card = public_tree_card(tree, today=today)
    caretaker = caretaker_of(tree)
    card["waterings"] = [
        {
            "day": timezone.localtime(watering.watered_at).date(),
            "by": watering.user.display_name,
        }
        for watering in watering_history(tree, limit=PUBLIC_HISTORY_LIMIT)
    ]
    card["caretaker"] = caretaker.display_name if caretaker else None
    card["caretaker_id"] = str(caretaker.pk) if caretaker else None
    return card


def active_species_names():
    """Names offered in the registration dropdown: catalogue entries still in use.

    Sorted alphabetically by the model's `ordering`; retired species stay in the database
    (trees keep their names) but disappear from the choices.
    """
    return list(TreeSpecies.objects.filter(is_active=True).values_list("name", flat=True))
