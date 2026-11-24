"""Reads behind the achievements page: one person's stats and the 30-day ranking.

Read from the domain tables, which are permanent — never from `activity_events`, which
`prune_activity` empties after a year (see `rules.py`).
"""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from accounts.models import User
from trees.models import Assignment, Tree, TreePhoto, Watering

from .models import UserBadge
from .rules import (
    BADGES,
    EVENING_HOURS,
    MORNING_HOURS,
    POINTS_PER_PHOTO,
    POINTS_PER_REGISTERED,
    POINTS_PER_TREE_CARED,
    POINTS_PER_TREE_DAY,
    WATERING,
    WATERING_NOTE,
    Stats,
    level_for,
    points_for,
)

RANKING_DAYS = 30
# How long a badge carries "Nowa!" on the page. Counted from `awarded_at`, not `seen_at`:
# the toast after an action marks a badge seen at once, and a toast that only counts a batch
# ("Masz 7 nowych odznak!") must still let the page show which ones they were.
NEW_FOR = timedelta(days=7)
RANKING_SIZE = 10


def _local_day():
    return TruncDate("watered_at", tzinfo=timezone.get_current_timezone())


def _in_care(care, tree_id, moment):
    return any(
        tree == tree_id and started <= moment and (ended is None or moment < ended)
        for tree, started, ended in care
    )


def user_stats(user, *, now=None) -> Stats:
    """Everything the rules need about one person: four small queries, however active.

    Waterings are read row by row (one person's history: hundreds of rows, not millions) and
    folded into tree-days in Python — the hour, the status, the species and the care at that
    moment are all per watering, and one pass is simpler than a query for each.
    """
    now = now or timezone.now()
    care = list(
        Assignment.objects.filter(user=user).values_list("tree_id", "started_at", "ended_at")
    )
    waterings = Watering.objects.filter(user=user).values_list(
        "tree_id",
        "watered_at",
        "tree_status",
        "tree__species",
        "tree__locality_id",
        "tree__created_by_id",
    )

    tree_days, neighbour, morning, evening, rescue = set(), set(), set(), set(), set()
    species, localities = set(), set()
    for tree_id, watered_at, status, kind, locality_id, created_by_id in waterings:
        local = timezone.localtime(watered_at)
        key = (tree_id, local.date())
        tree_days.add(key)
        species.add(kind.strip().lower())
        localities.add(locality_id)
        if local.hour in MORNING_HOURS:
            morning.add(key)
        if local.hour in EVENING_HOURS:
            evening.add(key)
        if status == Tree.Status.URGENT:
            rescue.add(key)
        if created_by_id != user.pk and not _in_care(care, tree_id, watered_at):
            neighbour.add(key)

    return Stats(
        tree_days=len(tree_days),
        watering_days=tuple(sorted({day for _, day in tree_days})),
        registered=Tree.objects.filter(created_by=user).count(),
        trees_cared=len({tree_id for tree_id, _, _ in care}),
        longest_care_days=max(
            ((ended or now) - started for _, started, ended in care), default=timedelta()
        ).days,
        photos=TreePhoto.objects.filter(uploaded_by=user).count(),
        neighbour_tree_days=len(neighbour),
        species=len(species - {""}),
        localities=len(localities),
        morning_tree_days=len(morning),
        evening_tree_days=len(evening),
        rescue_tree_days=len(rescue),
    )


def _start_of(day):
    return timezone.make_aware(datetime.combine(day, time.min))


@dataclass(frozen=True)
class RankingRow:
    rank: int
    user_id: object
    display_name: str
    points: int
    is_me: bool


def ranking_points(*, days=RANKING_DAYS, today=None) -> Counter:
    """Points earned in the last `days` local days (today included), by user id.

    Same rules as the level, limited to the window: tree-days watered, trees registered,
    trees taken into care (each tree once) and photos added inside it. Tree-days are counted
    in Python from distinct (user, tree, day) rows — a 30-day window keeps that list short.
    """
    today = today or timezone.localdate()
    since = _start_of(today - timedelta(days=days - 1))
    points = Counter()

    tree_days = (
        Watering.objects.filter(watered_at__gte=since)
        .annotate(day=_local_day())
        .values_list("user_id", "tree_id", "day")
        .distinct()
    )
    for user_id, _, _ in tree_days:
        points[user_id] += POINTS_PER_TREE_DAY

    grouped = (
        (Tree.objects.filter(created_at__gte=since), "created_by", "id", POINTS_PER_REGISTERED),
        (Assignment.objects.filter(started_at__gte=since), "user", "tree", POINTS_PER_TREE_CARED),
        (TreePhoto.objects.filter(created_at__gte=since), "uploaded_by", "id", POINTS_PER_PHOTO),
    )
    for query, owner, counted, worth in grouped:
        rows = query.values(owner).annotate(n=Count(counted, distinct=True))
        for row in rows:
            points[row[owner]] += row["n"] * worth
    return points


def leaderboard(*, me=None, days=RANKING_DAYS, size=RANKING_SIZE, today=None):
    """Top `size` volunteers of the window, plus `me` when outside it.

    Only active accounts, and no admins: the demo admin registered every tree, and a ranking
    is for the people doing the watering. Ties share a rank (1, 1, 3). Display names only —
    the page is for logged-in users, and an e-mail has no business on it.
    """
    points = ranking_points(days=days, today=today)
    people = User.objects.filter(pk__in=points.keys(), is_active=True).exclude(role=User.Role.ADMIN)
    names = dict(people.values_list("pk", "display_name"))
    ordered = sorted(names, key=lambda pk: (-points[pk], names[pk].lower()))

    rows, rank, previous = [], 0, None
    for position, pk in enumerate(ordered, start=1):
        if points[pk] != previous:
            rank, previous = position, points[pk]
        rows.append(
            RankingRow(
                rank=rank,
                user_id=pk,
                display_name=names[pk],
                points=points[pk],
                is_me=me is not None and pk == me.pk,
            )
        )

    top = rows[:size]
    mine = next((row for row in rows if row.is_me), None)
    return {
        "rows": top,
        # Shown under the table when the person is ranked, but not in the top.
        "me": mine if mine and mine not in top else None,
        "ranked": mine is not None,
        "days": days,
    }


def achievements(user, *, now=None):
    """Everything the achievements page and `/api/me/achievements` show."""
    now = now or timezone.now()
    stats = user_stats(user, now=now)
    points = points_for(stats)
    owned = {row.code: row for row in UserBadge.objects.filter(user=user)}
    return {
        "stats": stats,
        "points": points,
        "level": level_for(points),
        "badges": [
            {
                "badge": badge,
                "earned": badge.code in owned,
                "awarded_at": owned[badge.code].awarded_at if badge.code in owned else None,
                "new": badge.code in owned and owned[badge.code].awarded_at > now - NEW_FOR,
            }
            for badge in BADGES
        ],
        "earned_count": sum(1 for badge in BADGES if badge.code in owned),
        "watering_group": WATERING,
        "watering_note": WATERING_NOTE,
        "ranking": leaderboard(me=user),
    }
