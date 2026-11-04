"""Points, levels, streaks and badges — the pure rules, no database.

Thresholds are read from `rules.py`, not typed here: the numbers are a product decision and
may be tuned; what these tests pin is the behaviour at each boundary.
"""

from datetime import date, timedelta

import pytest

from gamification.rules import (
    BADGES,
    BADGES_BY_CODE,
    LEVELS,
    POINTS_PER_PHOTO,
    POINTS_PER_REGISTERED,
    POINTS_PER_TREE_CARED,
    POINTS_PER_TREE_DAY,
    Stats,
    earned_codes,
    level_for,
    longest_streak,
    points_for,
)

DAY = date(2026, 6, 1)


def days(*offsets):
    return tuple(DAY + timedelta(days=offset) for offset in offsets)


WEEK = days(*range(7))


class TestPoints:
    def test_nobody_starts_with_points(self):
        assert points_for(Stats()) == 0

    def test_each_kind_of_work_counts(self):
        stats = Stats(tree_days=3, registered=2, trees_cared=1, photos=4)

        assert points_for(stats) == (
            3 * POINTS_PER_TREE_DAY
            + 2 * POINTS_PER_REGISTERED
            + 1 * POINTS_PER_TREE_CARED
            + 4 * POINTS_PER_PHOTO
        )


class TestLevels:
    def test_levels_start_at_zero_and_rise(self):
        thresholds = [threshold for threshold, _, _ in LEVELS]
        assert thresholds[0] == 0
        assert thresholds == sorted(set(thresholds))

    @pytest.mark.parametrize("index", range(1, len(LEVELS)))
    def test_a_level_begins_exactly_at_its_threshold(self, index):
        threshold = LEVELS[index][0]

        assert level_for(threshold - 1).number == index
        assert level_for(threshold).number == index + 1

    def test_progress_towards_the_next_level(self):
        start, following = LEVELS[1][0], LEVELS[2][0]

        level = level_for(start + 7)

        assert (level.progress, level.span) == (7, following - start)
        assert level.to_next == following - start - 7
        assert level.next_name == LEVELS[2][2]

    def test_top_level_has_nowhere_further_to_go(self):
        level = level_for(LEVELS[-1][0] + 10_000)

        assert level.number == len(LEVELS)
        assert level.next_threshold is None
        assert (level.span, level.to_next) == (0, 0)


class TestStreak:
    def test_no_days_no_streak(self):
        assert longest_streak([]) == 0

    def test_consecutive_days(self):
        assert longest_streak(days(0, 1, 2)) == 3

    def test_a_gap_starts_again_and_the_longest_run_wins(self):
        assert longest_streak(days(0, 1, 3, 4, 5, 6, 9)) == 4

    def test_order_and_repeats_do_not_matter(self):
        assert longest_streak(days(2, 0, 1, 1, 2)) == 3

    def test_across_a_month_boundary(self):
        assert longest_streak([date(2026, 6, 30), date(2026, 7, 1)]) == 2


class TestBadges:
    def test_codes_are_unique(self):
        assert len(BADGES_BY_CODE) == len(BADGES)

    def test_codes_fit_the_column(self):
        assert all(len(badge.code) <= 32 for badge in BADGES)

    def test_a_newcomer_has_none(self):
        assert earned_codes(Stats()) == set()

    @pytest.mark.parametrize(
        ("code", "below", "at"),
        [
            ("first_drop", Stats(), Stats(tree_days=1)),
            ("watering_can", Stats(tree_days=9), Stats(tree_days=10)),
            ("sprinkler", Stats(tree_days=49), Stats(tree_days=50)),
            ("caretaker", Stats(), Stats(trees_cared=1)),
            ("grove_keeper", Stats(trees_cared=2), Stats(trees_cared=3)),
            ("faithful", Stats(longest_care_days=29), Stats(longest_care_days=30)),
            ("planter", Stats(), Stats(registered=1)),
            ("forester", Stats(registered=4), Stats(registered=5)),
            ("chronicler", Stats(), Stats(photos=1)),
            ("week_streak", Stats(watering_days=WEEK[:6]), Stats(watering_days=WEEK)),
        ],
    )  # fmt: skip
    def test_each_badge_at_its_boundary(self, code, below, at):
        assert code not in earned_codes(below)
        assert code in earned_codes(at)

    def test_seven_days_with_a_gap_is_not_a_week(self):
        assert "week_streak" not in earned_codes(Stats(watering_days=days(0, 1, 2, 4, 5, 6, 7)))
