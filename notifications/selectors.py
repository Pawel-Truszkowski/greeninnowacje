"""Queries behind the daily digest e-mails (spec §5.3).

Separate from `services.py` so that "who is in the digest" can be tested without sending
anything. One rule shapes `admin_overview()`: it returns counts and trees, never volunteer
names. An admin digest is an operational summary — the panel is the place to see who looks
after what, an e-mail forwarded to a grant officer is not.
"""

from collections import Counter

from django.db.models import Count, Exists, OuterRef

from accounts.models import User
from accounts.permissions import coordinator_localities
from trees.models import Assignment, Tree

from .models import Notification


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


def admin_overview(localities=None):
    """The digest's content: `{"localities": […], "orphans": […], "urgent_total": int}`.

    `orphans` are the URGENT trees nobody looks after — the section spec §5.3 asks to
    highlight, because they are the only ones no e-mail will reach a caretaker about.

    With `localities` it answers for that scope instead of the whole organisation, which is
    what a coordinator's digest needs. One function rather than two: the shape has to match
    exactly, since both feed `plan_digests` and the same kind of template.
    """
    active = Tree.objects.filter(lifecycle=Tree.Lifecycle.ACTIVE)
    if localities is not None:
        active = active.filter(locality__in=localities)

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


def active_coordinators():
    """Coordinators who can be written to. Admins are not here — they get the global digest."""
    return list(
        User.objects.filter(is_active=True, role=User.Role.COORDINATOR)
        .exclude(email="")
        .order_by("display_name")
    )


def coordinator_overview(user):
    """`admin_overview()` narrowed to one coordinator's localities."""
    return admin_overview(localities=coordinator_localities(user))


def area_volunteer_emails(user):
    """Active volunteers caring for trees in the coordinator's area, as a `QuerySet[User]`.

    The appeal goes to people with a stake in the area, not to everyone with an account:
    mailing strangers about a locality they have never visited is a different thing than
    asking for help, and only one of them is what the button says.
    """
    return (
        User.objects.filter(
            is_active=True,
            assignments__ended_at__isnull=True,
            assignments__tree__lifecycle=Tree.Lifecycle.ACTIVE,
            assignments__tree__locality__in=coordinator_localities(user),
        )
        .exclude(email="")
        .distinct()
        .order_by("display_name")
    )


def for_user(user):
    """This user's notices, newest first, ready to render.

    `select_related` on the tree and its locality: the list prints both on every row, and the
    index on `(user, read_at, -created_at)` is there so this and `unread_count` walk the same
    key.
    """
    return Notification.objects.filter(user=user).select_related("tree", "tree__locality")


def unread_count(user):
    """How many unread notices this user has. A count, not a list — it feeds a badge."""
    return Notification.objects.filter(user=user, read_at__isnull=True).count()
