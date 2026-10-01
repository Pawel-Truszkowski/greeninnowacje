"""Numbers for the admin dashboard (spec §4: GET /api/admin/stats).

Everything is aggregated in the database. Counting in Python would mean loading every
tree and watering into memory — fine for a demo, wrong for the first thousand trees.
"""

from datetime import timedelta

from django.db.models import Count, Exists, OuterRef, Q
from django.utils import timezone

from accounts.models import User
from trees.models import Assignment, Tree, TreePhoto, Watering

RECENT_DAYS = 7
PHOTO_LIST_LIMIT = 60
ACTIVITY_DAYS = 30


def _active_assignment():
    return Assignment.objects.filter(tree=OuterRef("pk"), ended_at__isnull=True)


def dashboard_stats(today=None, locality_ids=None):
    """Numbers for a dashboard. Without `locality_ids` the whole organisation, as before.

    `locality_ids=[]` is not the same as `None`: an empty list means a coordinator with no
    area assigned, and they must see zeros rather than everything.
    """
    today = today or timezone.localdate()
    week_ago = timezone.now() - timedelta(days=RECENT_DAYS)
    month_ago = timezone.now() - timedelta(days=ACTIVITY_DAYS)

    active_trees = Tree.objects.filter(lifecycle=Tree.Lifecycle.ACTIVE)
    archived_trees = Tree.objects.filter(lifecycle=Tree.Lifecycle.ARCHIVED)
    waterings = Watering.objects.all()
    volunteers = User.objects.filter(is_active=True)
    if locality_ids is not None:
        active_trees = active_trees.filter(locality_id__in=locality_ids)
        archived_trees = archived_trees.filter(locality_id__in=locality_ids)
        waterings = waterings.filter(tree__locality_id__in=locality_ids)
        volunteers = volunteers.filter(
            assignments__ended_at__isnull=True,
            assignments__tree__locality_id__in=locality_ids,
        ).distinct()
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
        "trees_archived": archived_trees.count(),
        "by_status": {status: by_status.get(status, 0) for status in Tree.Status.values},
        "localities": localities,
        "waterings_7": waterings.filter(watered_at__gte=week_ago).count(),
        "waterings_30": waterings.filter(watered_at__gte=month_ago).count(),
        "volunteers_total": volunteers.count(),
        "volunteers_active": volunteers.filter(waterings__watered_at__gte=month_ago)
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


def recent_photos(limit=PHOTO_LIST_LIMIT):
    """Latest photos from the whole system, for the moderation screen.

    Carries volunteer names, so — like `panel/export.py` — this is for the admin panel only
    and must never feed a public view.
    """
    return list(
        TreePhoto.objects.select_related("tree__locality", "uploaded_by").order_by("-created_at")[
            :limit
        ]
    )
