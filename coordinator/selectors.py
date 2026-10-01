"""What a coordinator sees in their area (UI doc §8.9).

Every query here is bounded by `coordinator_localities()` — the one place that decides what
"my area" means. Nothing in this module may widen that: a coordinator looking at a tree from
somebody else's locality is the failure this whole app exists to prevent.
"""

from datetime import timedelta

from django.db.models import Count, Exists, Max, OuterRef, Q, Subquery
from django.utils import timezone

from accounts.models import User
from accounts.permissions import coordinator_localities
from panel.selectors import ACTIVITY_DAYS, dashboard_stats
from trees.models import Assignment, Tree
from trees.selectors import by_urgency


def _active_assignment():
    return Assignment.objects.filter(tree=OuterRef("pk"), ended_at__isnull=True)


def area_trees(user):
    """Active trees in the coordinator's localities, most urgent first (spec §4 ordering)."""
    return (
        Tree.objects.filter(
            lifecycle=Tree.Lifecycle.ACTIVE,
            locality__in=coordinator_localities(user),
        )
        .select_related("locality")
        .annotate(
            status_rank=by_urgency(),
            last_watered_at=Max("waterings__watered_at"),
            # The row shows the caretaker and decides which action to offer; a subquery keeps
            # that at one query however long the list gets.
            has_caretaker=Exists(_active_assignment()),
            caretaker_name=Subquery(_active_assignment().values("user__display_name")[:1]),
        )
        # Never watered sorts first inside a status — it is the most urgent case there, and
        # PostgreSQL would otherwise push those NULLs to the end.
        .order_by("status_rank", "last_watered_at", "planted_on")
    )


def area_volunteers(user):
    """Volunteers caring for trees in the area, with the numbers the PoC table shows.

    The join on waterings is a LEFT one: a volunteer who took a tree and has not acted yet is
    exactly the person a coordinator is looking for, so they appear with zeros rather than
    disappearing.
    """
    localities = coordinator_localities(user)
    since = timezone.now() - timedelta(days=ACTIVITY_DAYS)
    cares_here = Q(assignments__tree__locality__in=localities) & Q(
        assignments__ended_at__isnull=True
    )
    watered_here = Q(waterings__tree__locality__in=localities)

    return (
        User.objects.filter(cares_here, assignments__tree__lifecycle=Tree.Lifecycle.ACTIVE)
        # Grouped by the user, not by the name: two volunteers may share a display name.
        .values("pk", "display_name")
        .annotate(
            # distinct=True throughout: joining assignments and waterings multiplies rows,
            # and without it every count would be the product of the two.
            trees=Count("assignments", filter=cares_here, distinct=True),
            waterings_30=Count(
                "waterings",
                filter=watered_here & Q(waterings__watered_at__gte=since),
                distinct=True,
            ),
            last_activity=Max("waterings__watered_at", filter=watered_here),
        )
        .order_by("display_name")
    )


def area_stats(user):
    """The tiles above the list — the panel's own numbers, narrowed to the area."""
    locality_ids = list(coordinator_localities(user).values_list("pk", flat=True))
    return dashboard_stats(locality_ids=locality_ids)
