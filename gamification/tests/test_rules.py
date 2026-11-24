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
    SEASON_MONTHS,
    Stats,
    best_season_weeks,
    earned_codes,
    level_for,
    longest_streak,
    longest_week_streak,
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


MONDAY = date(2026, 6, 1)  # DAY is a Monday — weeks below start on it


def weeks(*offsets, weekday=0):
    """One day in each given week after MONDAY (weekday 0 = Monday … 6 = Sunday)."""
    return tuple(MONDAY + timedelta(weeks=offset, days=weekday) for offset in offsets)


class TestWeekStreak:
    def test_no_days_no_weeks(self):
        assert longest_week_streak([]) == 0

    def test_one_watering_a_week_is_a_streak(self):
        assert longest_week_streak(weeks(0, 1, 2, 3)) == 4

    def test_sunday_then_monday_are_two_weeks(self):
        assert longest_week_streak([MONDAY + timedelta(days=6), MONDAY + timedelta(days=7)]) == 2

    def test_many_days_in_one_week_count_once(self):
        assert longest_week_streak(days(0, 1, 2, 3, 4, 5, 6)) == 1

    def test_a_skipped_week_starts_again(self):
        assert longest_week_streak(weeks(0, 1, 3, 4, 5)) == 3

    def test_across_new_year(self):
        assert longest_week_streak([date(2026, 12, 30), date(2027, 1, 6)]) == 2


class TestSeasonWeeks:
    def test_counts_distinct_weeks(self):
        assert best_season_weeks(weeks(0, 0, 1, 5) + weeks(1, weekday=3)) == 3

    def test_outside_the_season_does_not_count(self):
        winter = [date(2026, 1, 5), date(2026, 11, 9)]
        assert all(day.month not in SEASON_MONTHS for day in winter)

        assert best_season_weeks(winter) == 0

    def test_the_best_single_season_wins(self):
        this_year = weeks(0, 1, 2)
        last_year = [day.replace(year=2025) for day in weeks(0, 1)]

        assert best_season_weeks(this_year + tuple(last_year)) == 3


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
            ("three_drops", Stats(tree_days=2), Stats(tree_days=3)),
            ("garden_hose", Stats(tree_days=24), Stats(tree_days=25)),
            ("rain_cloud", Stats(tree_days=99), Stats(tree_days=100)),
            ("downpour", Stats(tree_days=249), Stats(tree_days=250)),
            ("rescuer", Stats(), Stats(rescue_tree_days=1)),
            ("guardian_angel", Stats(rescue_tree_days=9), Stats(rescue_tree_days=10)),
            ("steady_rhythm", Stats(watering_days=weeks(0, 1, 2)),
             Stats(watering_days=weeks(0, 1, 2, 3))),
            ("whole_season", Stats(watering_days=weeks(*range(11))),
             Stats(watering_days=weeks(*range(12)))),
            ("early_bird", Stats(morning_tree_days=2), Stats(morning_tree_days=3)),
            ("evening_waterer", Stats(evening_tree_days=2), Stats(evening_tree_days=3)),
            ("avenue_keeper", Stats(trees_cared=4), Stats(trees_cared=5)),
            ("forest_guardian", Stats(trees_cared=9), Stats(trees_cared=10)),
            ("first_week", Stats(longest_care_days=6), Stats(longest_care_days=7)),
            ("season_friend", Stats(longest_care_days=89), Stats(longest_care_days=90)),
            ("year_together", Stats(longest_care_days=364), Stats(longest_care_days=365)),
            ("good_neighbour", Stats(), Stats(neighbour_tree_days=1)),
            ("neighbourhood_help", Stats(neighbour_tree_days=9), Stats(neighbour_tree_days=10)),
            ("three_saplings", Stats(registered=2), Stats(registered=3)),
            ("grove_founder", Stats(registered=14), Stats(registered=15)),
            ("botanist", Stats(species=2), Stats(species=3)),
            ("dendrologist", Stats(species=4), Stats(species=5)),
            ("wanderer", Stats(localities=1), Stats(localities=2)),
            ("photo_reporter", Stats(photos=4), Stats(photos=5)),
            ("photo_chronicle", Stats(photos=19), Stats(photos=20)),
        ],
    )  # fmt: skip
    def test_each_badge_at_its_boundary(self, code, below, at):
        assert code not in earned_codes(below)
        assert code in earned_codes(at)

    def test_every_badge_has_a_boundary_test(self):
        tested = {
            "first_drop", "watering_can", "sprinkler", "caretaker", "grove_keeper", "faithful",
            "planter", "forester", "chronicler", "week_streak", "three_drops", "garden_hose",
            "rain_cloud", "downpour", "rescuer", "guardian_angel", "steady_rhythm",
            "whole_season", "early_bird", "evening_waterer", "avenue_keeper", "forest_guardian",
            "first_week", "season_friend", "year_together", "good_neighbour",
            "neighbourhood_help", "three_saplings", "grove_founder", "botanist", "dendrologist",
            "wanderer", "photo_reporter", "photo_chronicle",
        }  # fmt: skip
        assert tested == set(BADGES_BY_CODE)

    def test_each_group_is_listed_together(self):
        """The page regroups without sorting: a group split in two would show up twice."""
        order = [badge.group for badge in BADGES]
        seen = [group for i, group in enumerate(order) if i == 0 or order[i - 1] != group]

        assert len(seen) == len(set(seen))

    def test_icons_are_distinct(self):
        assert len({badge.icon for badge in BADGES}) == len(BADGES)

    def test_a_typical_first_day_leaves_most_badges_to_earn(self):
        """Register, take care, water and photograph one tree — the case that started this."""
        first_day = Stats(
            tree_days=1, watering_days=(DAY,), registered=1, trees_cared=1, photos=1, species=1,
            localities=1,
        )  # fmt: skip

        assert len(earned_codes(first_day)) <= len(BADGES) // 5

    def test_seven_days_with_a_gap_is_not_a_week(self):
        assert "week_streak" not in earned_codes(Stats(watering_days=days(0, 1, 2, 4, 5, 6, 7)))
