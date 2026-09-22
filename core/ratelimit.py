"""Rate limiting on PostgreSQL (spec §7) — no Redis, shared by all app processes.

Counters are incremented with a single INSERT … ON CONFLICT … RETURNING, which is atomic,
so concurrent requests cannot slip past the limit (unlike get-then-set cache counters).
Fixed windows: a burst straddling a window boundary may see up to 2× the limit.
"""

import functools
import re
from datetime import UTC, datetime, timedelta

from django.db import connection
from django.utils import timezone

from .models import RateLimitCounter
from .net import client_ip

_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_RATE_RE = re.compile(r"^(\d+)/(\d*)([smhd])$")
_RETENTION = timedelta(days=1)


def parse_rate(rate):
    """'10/15m' → (10, 900)."""
    match = _RATE_RE.match(rate)
    if not match:
        raise ValueError(f"Invalid rate: {rate!r}")
    limit, multiplier, unit = match.groups()
    return int(limit), int(multiplier or 1) * _UNITS[unit]


def hit(key, rate):
    """Count one hit for `key`; return True while the hit is within the limit."""
    limit, period = parse_rate(rate)
    now = timezone.now()
    window_start = datetime.fromtimestamp(now.timestamp() // period * period, tz=UTC)
    table = RateLimitCounter._meta.db_table
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO {table} (key, window_start, count) VALUES (%s, %s, 1)
            ON CONFLICT (key, window_start) DO UPDATE SET count = {table}.count + 1
            RETURNING count
            """,  # noqa: S608 — table name is a constant, values are parameterised
            [key, window_start],
        )
        (count,) = cursor.fetchone()
    RateLimitCounter.objects.filter(window_start__lt=now - _RETENTION).delete()
    return count <= limit


def _request_key(request, key):
    if key == "ip":
        return client_ip(request)
    if key == "user":
        return str(request.user.pk) if request.user.is_authenticated else client_ip(request)
    raise ValueError(f"Unknown rate limit key: {key!r}")


def rate_limit(group, rate, key="ip", methods=("POST",)):
    """View decorator: sets `request.limited`; the view decides how to respond.

    `rate` may be a string or a zero-argument callable (lets settings be read lazily).
    """

    def decorator(view):
        @functools.wraps(view)
        def wrapper(request, *args, **kwargs):
            request.limited = False
            if request.method in methods:
                current = rate() if callable(rate) else rate
                bucket = f"{group}:{_request_key(request, key)}"
                request.limited = not hit(bucket, current)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator
