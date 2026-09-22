from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from core.models import RateLimitCounter
from core.ratelimit import hit, parse_rate

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("rate", "expected"),
    [("10/15m", (10, 900)), ("30/m", (30, 60)), ("5/2h", (5, 7200)), ("1/d", (1, 86400))],
)
def test_parse_rate(rate, expected):
    assert parse_rate(rate) == expected


@pytest.mark.parametrize("rate", ["10", "abc/m", "10/15x", ""])
def test_parse_rate_rejects_garbage(rate):
    with pytest.raises(ValueError):
        parse_rate(rate)


def test_allows_up_to_limit_then_blocks():
    assert [hit("k", "3/m") for _ in range(4)] == [True, True, True, False]


def test_keys_are_independent():
    for _ in range(3):
        hit("a", "3/m")
    assert hit("b", "3/m")


def test_new_window_resets_counter():
    start = timezone.now().replace(second=0, microsecond=0)
    with mock.patch("core.ratelimit.timezone.now", return_value=start):
        for _ in range(3):
            hit("k", "3/m")
        assert not hit("k", "3/m")
    with mock.patch("core.ratelimit.timezone.now", return_value=start + timedelta(minutes=1)):
        assert hit("k", "3/m")


def test_expired_counters_purged():
    old = timezone.now() - timedelta(days=2)
    RateLimitCounter.objects.create(key="stary", window_start=old, count=5)
    hit("k", "3/m")
    assert not RateLimitCounter.objects.filter(key="stary").exists()
