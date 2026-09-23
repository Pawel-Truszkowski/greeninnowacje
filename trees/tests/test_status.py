"""Status algorithm edge cases (spec §6.2)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from core.models import DroughtConfig
from trees.models import Tree
from trees.status import StatusInputs, compute_status, last_rain_day, rain_total_mm

TODAY = date(2026, 7, 15)
CONFIG = DroughtConfig(
    rain_window_days=5, rain_threshold_mm=Decimal("10"), days_soon=3, days_urgent=5
)


def rainfall(*values, days=5, today=TODAY):
    """Readings for the window, oldest first; None means 'no reading'."""
    values = list(values) or [Decimal("0")] * days
    first = today - timedelta(days=len(values) - 1)
    return [(first + timedelta(days=offset), value) for offset, value in enumerate(values)]


def inputs(**overrides):
    defaults = {
        "today": TODAY,
        "planted_on": TODAY - timedelta(days=100),
        "created_on": TODAY - timedelta(days=100),
        "last_watered_on": None,
        "rainfall": rainfall(),
    }
    return StatusInputs(**(defaults | overrides))


def mm(*values):
    return [None if value is None else Decimal(str(value)) for value in values]


class TestHelpers:
    def test_missing_readings_do_not_break_the_sum(self):
        assert rain_total_mm(rainfall(*mm(2, None, 3, None, 1))) == Decimal("6")

    def test_last_rain_day_ignores_drizzle_below_1mm(self):
        series = rainfall(*mm(5, 0, 0.4, 0, 0))
        assert last_rain_day(series) == TODAY - timedelta(days=4)

    def test_last_rain_day_without_rain(self):
        assert last_rain_day(rainfall(*mm(0, 0, 0, 0, 0))) is None


class TestCompute:
    def test_enough_rain_means_ok(self):
        result = compute_status(inputs(rainfall=rainfall(*mm(4, 4, 2, 0, 0))), CONFIG)
        assert result == Tree.Status.OK

    def test_rain_just_below_threshold_is_not_enough(self):
        result = compute_status(inputs(rainfall=rainfall(*mm(4, 4, 1.9, 0, 0))), CONFIG)
        assert result != Tree.Status.OK

    @pytest.mark.parametrize("days_ago", [0, 1, 3])
    def test_recently_watered_is_ok(self, days_ago):
        result = compute_status(inputs(last_watered_on=TODAY - timedelta(days=days_ago)), CONFIG)
        assert result == Tree.Status.OK

    @pytest.mark.parametrize(
        ("days_ago", "expected"),
        [(4, Tree.Status.SOON), (5, Tree.Status.URGENT), (30, Tree.Status.URGENT)],
    )
    def test_dry_days_counted_from_last_watering(self, days_ago, expected):
        result = compute_status(inputs(last_watered_on=TODAY - timedelta(days=days_ago)), CONFIG)
        assert result == expected

    def test_rain_resets_the_dry_count_even_without_watering(self):
        """Spec §5.6: rain in the locality means the tree is not left as 'needs water'."""
        series = rainfall(*mm(0, 0, 3, 0, 0))  # 2 days ago, below the OK threshold
        result = compute_status(
            inputs(last_watered_on=TODAY - timedelta(days=40), rainfall=series), CONFIG
        )
        assert result == Tree.Status.SOON

    def test_missing_readings_count_as_no_rain(self):
        series = rainfall(*mm(None, None, None, None, None))
        result = compute_status(
            inputs(last_watered_on=TODAY - timedelta(days=6), rainfall=series), CONFIG
        )
        assert result == Tree.Status.URGENT

    def test_planting_counts_as_watering(self):
        """A tree planted today was watered today (rollout guide 1.A.7)."""
        fresh = inputs(planted_on=TODAY, created_on=TODAY)
        assert compute_status(fresh, CONFIG) == Tree.Status.OK

    @pytest.mark.parametrize(
        ("planted_days_ago", "expected"),
        [(3, Tree.Status.OK), (4, Tree.Status.SOON), (5, Tree.Status.URGENT)],
    )
    def test_dry_days_counted_from_planting_when_never_watered(self, planted_days_ago, expected):
        never_watered = inputs(
            planted_on=TODAY - timedelta(days=planted_days_ago),
            created_on=TODAY - timedelta(days=planted_days_ago),
        )
        assert compute_status(never_watered, CONFIG) == expected

    def test_future_planting_date_does_not_break_the_count(self):
        typo = inputs(planted_on=TODAY + timedelta(days=30), created_on=TODAY)
        assert compute_status(typo, CONFIG) == Tree.Status.OK


class TestRegistrationGrace:
    """Spec §6.2: a newly registered tree must not be URGENT straight away."""

    def test_old_tree_registered_today_is_not_urgent(self):
        just_added = inputs(planted_on=TODAY - timedelta(days=200), created_on=TODAY)
        assert compute_status(just_added, CONFIG) == Tree.Status.SOON

    def test_grace_ends_after_days_soon(self):
        settled = inputs(
            planted_on=TODAY - timedelta(days=200),
            created_on=TODAY - timedelta(days=CONFIG.days_soon),
        )
        assert compute_status(settled, CONFIG) == Tree.Status.URGENT

    def test_grace_does_not_hide_rain(self):
        """Grace only caps the status; rain still makes it OK."""
        rained = inputs(
            planted_on=TODAY - timedelta(days=200),
            created_on=TODAY,
            rainfall=rainfall(*mm(6, 5, 0, 0, 0)),
        )
        assert compute_status(rained, CONFIG) == Tree.Status.OK


class TestConfig:
    def test_thresholds_come_from_config(self):
        lenient = DroughtConfig(
            rain_window_days=5, rain_threshold_mm=Decimal("10"), days_soon=3, days_urgent=10
        )
        watered = inputs(last_watered_on=TODAY - timedelta(days=6))
        assert compute_status(watered, CONFIG) == Tree.Status.URGENT
        assert compute_status(watered, lenient) == Tree.Status.SOON
