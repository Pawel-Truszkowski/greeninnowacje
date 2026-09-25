"""Numbers for the admin dashboard (spec §4: GET /api/admin/stats).

Everything is aggregated in the database. Counting in Python would mean loading every
tree and watering into memory — fine for a demo, wrong for the first thousand trees.
"""

from datetime import timedelta

from django.db.models import Count, Exists, OuterRef, Q
from django.utils import timezone

from accounts.models import User
from trees.models import Assignment, Tree, Watering

RECENT_DAYS = 7
ACTIVITY_DAYS = 30


def _active_assignment():
    return Assignment.objects.filter(tree=OuterRef("pk"), ended_at__isnull=True)


def dashboard_stats(today=None):
    today = today or timezone.localdate()
    week_ago = timezone.now() - timedelta(days=RECENT_DAYS)
    month_ago = timezone.now() - timedelta(days=ACTIVITY_DAYS)

    active_trees = Tree.objects.filter(lifecycle=Tree.Lifecycle.ACTIVE)
    by_status = dict(
        active_trees.values_list("status")
        .annotate(total=Count("id"))
        .values_list("status", "total")
    )
    tended = Exists(_active_assignment())
    localities = list(
        active_trees.annotate(has_caretaker=tended)
        .values("locality__name")
        .annotate(
            total=Count("id"),
            ok=Count("id", filter=Q(status=Tree.Status.OK)),
            soon=Count("id", filter=Q(status=Tree.Status.SOON)),
            urgent=Count("id", filter=Q(status=Tree.Status.URGENT)),
            orphans=Count("id", filter=Q(has_caretaker=False)),
        )
        .order_by("locality__name")
    )

    without_caretaker = active_trees.annotate(has_caretaker=tended).filter(has_caretaker=False)

    return {
        "trees_total": active_trees.count(),
        "trees_archived": Tree.objects.filter(lifecycle=Tree.Lifecycle.ARCHIVED).count(),
        "by_status": {status: by_status.get(status, 0) for status in Tree.Status.values},
        "localities": localities,
        "waterings_7": Watering.objects.filter(watered_at__gte=week_ago).count(),
        "waterings_30": Watering.objects.filter(watered_at__gte=month_ago).count(),
        "volunteers_total": User.objects.filter(is_active=True).count(),
        "volunteers_active": User.objects.filter(
            is_active=True, waterings__watered_at__gte=month_ago
        )
        .distinct()
        .count(),
        "without_caretaker": without_caretaker.count(),
        # Two separate problems, two separate lists — as in the PoC, where a healthy tree
        # with nobody looking after it is still something the admin has to act on.
        "needs_water": list(
            active_trees.filter(status=Tree.Status.URGENT)
            .annotate(has_caretaker=tended)
            .select_related("locality")[:20]
        ),
        "needs_caretaker": list(without_caretaker.select_related("locality")[:20]),
        "today": today,
    }
