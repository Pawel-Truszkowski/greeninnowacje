"""Writes: hand out the badges a person has earned, and tell them once.

`award_badges` is called from `trees/services.py` inside the same transaction as the action
that earned the badge, so a refused watering or a lost caretaker race awards nothing. The
achievements page calls it as well — that is how a time-based badge ("30 dni opieki"), earned
without any action, shows up.
"""

from django.utils import timezone

from .models import UserBadge
from .rules import earned_codes
from .selectors import user_stats


def award_badges(user):
    """Store every badge `user` qualifies for and does not have yet; returns the new codes."""
    if user is None or not user.is_authenticated:
        return []
    owned = set(UserBadge.objects.filter(user=user).values_list("code", flat=True))
    new = sorted(earned_codes(user_stats(user)) - owned)
    # ignore_conflicts: two waterings at once may both decide a badge is due; the unique
    # constraint keeps one, and neither request fails.
    UserBadge.objects.bulk_create(
        [UserBadge(user=user, code=code) for code in new], ignore_conflicts=True
    )
    return new


def take_unseen(user):
    """Badges the person has not been told about, in the order earned — then marks them seen."""
    unseen = list(UserBadge.objects.filter(user=user, seen_at__isnull=True))
    if unseen:
        UserBadge.objects.filter(pk__in=[row.pk for row in unseen]).update(seen_at=timezone.now())
    return [row.badge for row in unseen if row.badge]


def new_badges_message(badges):
    """One toast, however many badges came at once (registration with a photo gives two)."""
    if not badges:
        return None
    if len(badges) == 1:
        badge = badges[0]
        return f"🏅 Nowa odznaka: {badge.icon} {badge.name}! Zajrzyj do Osiągnięć."
    names = ", ".join(f"{badge.icon} {badge.name}" for badge in badges)
    return f"🏅 Nowe odznaki: {names}! Zajrzyj do Osiągnięć."
