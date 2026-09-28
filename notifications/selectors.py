"""Queries behind the daily digest e-mails (spec §5.3).

Separate from `services.py` so that "who is in the digest" can be tested without sending
anything. One rule shapes `admin_overview()`: it returns counts and trees, never volunteer
names. An admin digest is an operational summary — the panel is the place to see who looks
after what, an e-mail forwarded to a grant officer is not.
"""

from collections import Counter

from django.db.models import Count, Exists, OuterRef

from accounts.models import User
from trees.models import Assignment, Tree


def _active_assignment():
    return Assignment.objects.filter(tree=OuterRef("pk"), ended_at__isnull=True)


def urgent_by_caretaker():
    """Caretakers with their URGENT trees: `[(user, [tree, …]), …]`.

    One query, grouped in Python — the e-mail needs whole trees (species, locality, id for
    the link), not aggregates. Ordered so the message reads the same on every run.
    """
    assignments = (
        Assignment.objects.filter(
            ended_at__isnull=True,
            tree__lifecycle=Tree.Lifecycle.ACTIVE,
            tree__status=Tree.Status.URGENT,
            user__is_active=True,
        )
        .exclude(user__email="")
        .select_related("user", "tree__locality")
        .order_by("user__display_name", "tree__locality__name", "tree__planted_on")
    )

    grouped = {}
    for assignment in assignments:
        grouped.setdefault(assignment.user, []).append(assignment.tree)
    return list(grouped.items())


def admin_overview():
    """The admin digest's content: `{"localities": […], "orphans": […], "urgent_total": int}`.

    `orphans` are the URGENT trees nobody looks after — the section spec §5.3 asks to
    highlight, because they are the only ones no e-mail will reach a caretaker about.
    """
    active = Tree.objects.filter(lifecycle=Tree.Lifecycle.ACTIVE)

    orphans = list(
        active.filter(status=Tree.Status.URGENT)
        .annotate(has_caretaker=Exists(_active_assignment()))
        .filter(has_caretaker=False)
        .select_related("locality")
        .order_by("locality__name", "planted_on")
    )
    orphans_per_locality = Counter(tree.locality.name for tree in orphans)

    localities = [
        {
            "name": row["locality__name"],
            "urgent": row["urgent"],
            "orphans": orphans_per_locality[row["locality__name"]],
        }
        for row in active.filter(status=Tree.Status.URGENT)
        .values("locality__name")
        .annotate(urgent=Count("id"))
        .order_by("locality__name")
    ]

    return {
        "localities": localities,
        "orphans": orphans,
        "urgent_total": sum(row["urgent"] for row in localities),
    }


def active_admins():
    """Admins who can be written to. Inactive accounts and empty e-mails drop out here."""
    return list(
        User.objects.filter(is_active=True, role=User.Role.ADMIN)
        .exclude(email="")
        .order_by("display_name")
    )
