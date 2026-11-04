"""Numbers for the activity screen (`/admin/aktywnosc`, `/api/admin/activity`).

Windows are calendar days in local time with today included — „7 dni" is today and the six
days before it, the way a person reads a chart ending today. Everything is aggregated in
the database: a constant number of queries however many people use the app.
"""

from datetime import datetime, time, timedelta

from django.db.models import Count, Max, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from accounts.models import User

from .models import ActivityEvent

Kind = ActivityEvent.Kind

INTERACTION_KINDS = (
    Kind.WATERING,
    Kind.TREE_REGISTERED,
    Kind.PHOTO_ADDED,
    Kind.CARE_TAKEN,
    Kind.CARE_RELEASED,
)
CHART_DAYS = 30


def fill_days(counts, *, today, days):
    """`[(day, count), …]` for the `days` days ending today, oldest first, gaps as zero."""
    first = today - timedelta(days=days - 1)
    return [
        (first + timedelta(days=offset), counts.get(first + timedelta(days=offset), 0))
        for offset in range(days)
    ]


def _start_of(day):
    return timezone.make_aware(datetime.combine(day, time.min))


def activity_summary(today=None):
    today = today or timezone.localdate()
    end = _start_of(today + timedelta(days=1))
    since_7 = _start_of(today - timedelta(days=6))
    since_30 = _start_of(today - timedelta(days=CHART_DAYS - 1))

    window = ActivityEvent.objects.filter(created_at__gte=since_30, created_at__lt=end)
    in_7 = Q(created_at__gte=since_7)
    login = Q(kind=Kind.LOGIN)
    interaction = Q(kind__in=INTERACTION_KINDS)

    totals = window.aggregate(
        logins_7=Count("id", filter=login & in_7),
        logins_30=Count("id", filter=login),
        active_users_7=Count("user", filter=in_7, distinct=True),
        active_users_30=Count("user", distinct=True),
        signups_30=Count("id", filter=Q(kind=Kind.SIGNUP)),
        failed_logins_7=Count("id", filter=Q(kind=Kind.LOGIN_FAILED) & in_7),
        card_views_30=Count("id", filter=Q(kind=Kind.CARD_VIEW)),
    )

    per_day = (
        window.annotate(day=TruncDate("created_at", tzinfo=timezone.get_current_timezone()))
        .values("day")
        .annotate(logins=Count("id", filter=login), interactions=Count("id", filter=interaction))
    )
    logins = {row["day"]: row["logins"] for row in per_day}
    interactions = {row["day"]: row["interactions"] for row in per_day}
    daily = [
        {"day": day, "logins": count, "interactions": interactions.get(day, 0)}
        for day, count in fill_days(logins, today=today, days=CHART_DAYS)
    ]

    people_rows = list(
        window.filter(user__isnull=False)
        .values("user")
        .annotate(
            last_seen=Max("created_at"),
            logins_30=Count("id", filter=login),
            interactions_30=Count("id", filter=interaction),
        )
        .order_by("-last_seen")
    )
    users = User.objects.in_bulk([row["user"] for row in people_rows])
    people = [
        {
            "user": users[row["user"]],
            "last_login": users[row["user"]].last_login,
            "last_seen": row["last_seen"],
            "logins_30": row["logins_30"],
            "interactions_30": row["interactions_30"],
        }
        for row in people_rows
    ]

    return {**totals, "daily": daily, "people": people, "today": today}
