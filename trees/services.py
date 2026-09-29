"""Write-side operations on trees (spec §4, volunteer endpoints).

Views — HTML and JSON alike — call these; they own the invariants, so a rule like
"one active caretaker" or "recompute the status right after watering" cannot be
forgotten in one entry point and remembered in another.
"""

import logging
from collections import Counter
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.db.models import BooleanField, Case, F, IntegerField, Max, Value, When
from django.utils import timezone

from core.models import load_drought_config
from weather.services import backfill_locality

from .geo import DUPLICATE_RADIUS_M, bbox_around, haversine_m
from .images import process_upload
from .models import Assignment, Locality, Tree, TreePhoto, Watering
from .nominatim import reverse_locality
from .selectors import last_finished_day, weather_series
from .status import StatusInputs, compute_status, missing_rain_days

logger = logging.getLogger(__name__)


class CaretakerConflict(Exception):
    """Somebody else is already looking after this tree."""


def _rainfall_window(locality_id, today, config):
    window = weather_series(
        locality_id, days=config.rain_window_days, end_day=last_finished_day(today)
    )
    return [(day["day"], day["precip_mm"]) for day in window]


def _warn_about_gaps(locality_id, rainfall, config):
    """One warning per locality: the gap is in the weather, not in the tree."""
    missing = missing_rain_days(rainfall)
    if missing:
        # Treated as 0 mm, but a gap means the status may be based on partial data.
        logger.warning(
            "Niepełne dane pogodowe dla miejscowości %s: brakuje %d z %d dni (%s)",
            locality_id,
            len(missing),
            config.rain_window_days,
            ", ".join(day.isoformat() for day in missing),
        )


def _build_inputs(tree, today, rainfall, last_watered_at):
    return StatusInputs(
        today=today,
        planted_on=tree.planted_on,
        created_on=timezone.localtime(tree.created_at).date(),
        last_watered_on=timezone.localtime(last_watered_at).date() if last_watered_at else None,
        rainfall=rainfall,
    )


def _status_inputs(tree, today, config):
    last_watered_at = tree.waterings.aggregate(last=Max("watered_at"))["last"]
    return _build_inputs(
        tree, today, _rainfall_window(tree.locality_id, today, config), last_watered_at
    )


def recompute_tree_status(tree, today=None, save=True):
    """Recompute one tree's status; writes only when it actually changed (spec §6.2)."""
    today = today or timezone.localdate()
    config = load_drought_config()
    inputs = _status_inputs(tree, today, config)
    _warn_about_gaps(tree.locality_id, inputs.rainfall, config)

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


class DuplicateTree(Exception):
    """A tree is already registered at (practically) the same spot."""

    def __init__(self, existing, distance_m):
        super().__init__("W tym miejscu jest już zarejestrowane drzewo.")
        self.existing = existing
        self.distance_m = distance_m


class LocalityUnknown(Exception):
    """Reverse geocoding failed and the volunteer did not supply a name."""


def find_duplicate(lat, lng, radius_m=DUPLICATE_RADIUS_M):
    """Return (tree, distance_m) for an active tree within `radius_m`, else None.

    Two volunteers registering the same tree at an event is the realistic case this
    guards against (spec §4: respond 409 and let the user confirm).

    Species is deliberately ignored: phone GPS is accurate to 3–8 m and volunteers are
    not botanists, so "a different species 1.5 m away" is more likely to be the same tree
    named differently than two trees planted that close. The user has the final say via
    `force`. Archived trees do not count — their spot is free for a new planting.
    """
    box = bbox_around(lat, lng, radius_m)
    candidates = Tree.objects.filter(
        lifecycle=Tree.Lifecycle.ACTIVE,
        lat__gte=box["min_lat"],
        lat__lte=box["max_lat"],
        lng__gte=box["min_lng"],
        lng__lte=box["max_lng"],
    )
    # The box is a generous prefilter — its corners lie further away than radius_m — so
    # the exact distance decides. It normally leaves zero or one candidate.
    nearby = [
        (tree, distance)
        for tree, distance in (
            (tree, haversine_m(lat, lng, tree.lat, tree.lng)) for tree in candidates
        )
        if distance <= radius_m
    ]
    if not nearby:
        return None
    return min(nearby, key=lambda pair: pair[1])


def resolve_locality(lat, lng, name=None):
    """Find or create the locality for these coordinates (spec §5.2).

    A name typed by the volunteer wins over the geocoder; matching is case-insensitive
    so "sierpc" and "Sierpc" stay one locality. A brand-new locality takes the tree's
    coordinates as its centroid — good enough for fetching weather.
    """
    name = (name or "").strip() or reverse_locality(lat, lng)
    if not name:
        raise LocalityUnknown("Nie udało się ustalić miejscowości.")

    existing = Locality.objects.filter(name__iexact=name).first()
    if existing:
        return existing

    locality = Locality.objects.create(name=name, lat=lat, lng=lng)
    # After the commit, not inside it: an HTTP call would otherwise hold the transaction
    # open, and a tree must stay registered even if the weather service is down.
    transaction.on_commit(lambda: backfill_locality(locality))
    return locality


@transaction.atomic
def register_tree(user, *, locality_name=None, force=False, **fields):
    """Register a tree: duplicate check, locality, then the tree itself (spec §4)."""
    if not force:
        duplicate = find_duplicate(fields["lat"], fields["lng"])
        if duplicate:
            existing, distance_m = duplicate
            raise DuplicateTree(existing, distance_m)

    locality = resolve_locality(fields["lat"], fields["lng"], locality_name)
    tree = Tree.objects.create(created_by=user, locality=locality, **fields)
    recompute_tree_status(tree)
    return tree


@dataclass(frozen=True)
class RecomputeResult:
    checked: int
    changed: int
    counts: dict[str, int]


def recompute_all(*, today=None, locality_id=None, save=True) -> RecomputeResult:
    """Recompute every active tree (spec §6, the 07:00 job and the admin's "recompute now").

    Reads in bulk on purpose: the config once, the weather once per locality and the last
    watering as an annotation. Done tree by tree this would be three queries each — fine
    for one watering, wasteful for a whole database.
    """
    today = today or timezone.localdate()
    config = load_drought_config()

    trees = Tree.objects.filter(lifecycle=Tree.Lifecycle.ACTIVE).annotate(
        last_watered_at=Max("waterings__watered_at")
    )
    if locality_id:
        trees = trees.filter(locality_id=locality_id)
    trees = list(trees)

    windows = {}
    for tree_locality_id in {tree.locality_id for tree in trees}:
        rainfall = _rainfall_window(tree_locality_id, today, config)
        _warn_about_gaps(tree_locality_id, rainfall, config)
        windows[tree_locality_id] = rainfall

    counts = Counter()
    changed = []
    for tree in trees:
        status = compute_status(
            _build_inputs(tree, today, windows[tree.locality_id], tree.last_watered_at), config
        )
        counts[status] += 1
        if status != tree.status:
            tree.status = status
            changed.append(tree)

    if save and changed:
        Tree.objects.bulk_update(changed, ["status"])

    return RecomputeResult(checked=len(trees), changed=len(changed), counts=dict(counts))


# --- photos (Etap 2) -----------------------------------------------------------------

MAX_PHOTOS_PER_TREE = 24


class PhotoNotAllowed(Exception):
    """This user may not add or remove this photo. The message reaches the user, so PL."""


def can_manage_photos(tree, user):
    """Caretaker, whoever registered the tree, or an admin.

    Narrower than watering, which any logged-in volunteer may record: a watering is a fact
    about the tree, a photo is content nobody moderates.
    """
    # First, because AnonymousUser has no `is_app_admin`.
    if not user.is_authenticated:
        return False
    if user.is_app_admin or tree.created_by_id == user.pk:
        return True
    return caretaker_of(tree) == user


def add_photo(tree, user, upload):
    """Store one photo of `tree`; `InvalidImage` passes through for a file we cannot use."""
    if not can_manage_photos(tree, user):
        raise PhotoNotAllowed("Zdjęcie może dodać opiekun drzewa, jego autor lub administrator.")
    if TreePhoto.objects.filter(tree=tree).count() >= MAX_PHOTOS_PER_TREE:
        raise PhotoNotAllowed(f"To drzewo ma już maksymalną liczbę zdjęć ({MAX_PHOTOS_PER_TREE}).")

    # Last, so a refused upload never costs a decode.
    processed = process_upload(upload)
    return TreePhoto.objects.create(
        tree=tree,
        uploaded_by=user,
        image=processed.file,
        width=processed.width,
        height=processed.height,
    )


def delete_photo(photo, user):
    """Remove a photo and its file — its author or an admin may.

    A real delete, unlike trees, which are only archived: a photo can show a person, and that
    person may ask for it to go.
    """
    if not user.is_authenticated or not (user.is_app_admin or photo.uploaded_by_id == user.pk):
        raise PhotoNotAllowed("Usunąć zdjęcie może jego autor lub administrator.")

    # Deleting the row leaves the file behind, and an orphan is still a photo of somebody.
    photo.image.delete(save=False)
    photo.delete()
