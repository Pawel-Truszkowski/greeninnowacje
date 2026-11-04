"""Numbers for the activity screen. Written before the code.

Windows are calendar days in local time, today included: „7 dni" means today and the six
days before it, the same way a person reads a chart that ends today. Events are placed at
local noon so no test depends on the clock or the time zone of the machine running it.

`fill_days` is a pure function — no database — like `trees/status.py`.
"""

from datetime import date, datetime, time, timedelta

import pytest
from django.utils import timezone

from activity.models import ActivityEvent
from activity.selectors import INTERACTION_KINDS, activity_summary, fill_days
from factories import TreeFactory, UserFactory

Kind = ActivityEvent.Kind
TODAY = date(2026, 11, 4)


def at(days_ago, today=TODAY):
    return timezone.make_aware(datetime.combine(today - timedelta(days=days_ago), time(12)))


def log(kind, user=None, tree=None, days_ago=0):
    return ActivityEvent.objects.create(kind=kind, user=user, tree=tree, created_at=at(days_ago))


def quiet_user(**fields):
    """A user without the sign-up event their creation writes, so tests start from zero."""
    person = UserFactory(**fields)
    ActivityEvent.objects.filter(user=person).delete()
    return person


def quiet_tree():
    """A tree whose author's sign-up event is gone too — the summary sees only what we log."""
    tree = TreeFactory()
    ActivityEvent.objects.all().delete()
    return tree


class TestFillDays:
    def test_one_entry_per_day_oldest_first_ending_today(self):
        days = fill_days({}, today=TODAY, days=3)

        assert days == [(date(2026, 11, 2), 0), (date(2026, 11, 3), 0), (TODAY, 0)]

    def test_known_days_keep_their_counts(self):
        counts = {date(2026, 11, 3): 4, TODAY: 1}

        assert fill_days(counts, today=TODAY, days=3)[1:] == [(date(2026, 11, 3), 4), (TODAY, 1)]

    def test_days_outside_the_window_are_dropped(self):
        counts = {date(2026, 10, 1): 9}

        assert sum(count for _, count in fill_days(counts, today=TODAY, days=30)) == 0


def test_interactions_are_the_five_tree_actions():
    assert set(INTERACTION_KINDS) == {
        Kind.WATERING,
        Kind.TREE_REGISTERED,
        Kind.PHOTO_ADDED,
        Kind.CARE_TAKEN,
        Kind.CARE_RELEASED,
    }


@pytest.mark.django_db
class TestSummary:
    def test_empty_database_gives_zeros_not_errors(self):
        ActivityEvent.objects.all().delete()

        summary = activity_summary(today=TODAY)

        for key in (
            "logins_7",
            "logins_30",
            "active_users_7",
            "active_users_30",
            "signups_30",
            "failed_logins_7",
            "card_views_30",
        ):
            assert summary[key] == 0, key
        assert len(summary["daily"]) == 30
        assert summary["people"] == []

    def test_login_windows_include_today_and_stop_at_the_edge(self):
        person = quiet_user()
        for days_ago in (0, 6, 7, 29, 30):
            log(Kind.LOGIN, person, days_ago=days_ago)

        summary = activity_summary(today=TODAY)

        assert summary["logins_7"] == 2  # today and six days ago
        assert summary["logins_30"] == 4  # everything but day 30

    def test_active_users_are_distinct_people_with_any_event(self):
        anna, jan, ewa = quiet_user(), quiet_user(), quiet_user()
        tree = quiet_tree()
        log(Kind.LOGIN, anna)
        log(Kind.LOGIN, anna, days_ago=1)
        log(Kind.WATERING, jan, tree, days_ago=10)
        log(Kind.LOGIN, ewa, days_ago=40)

        summary = activity_summary(today=TODAY)

        assert summary["active_users_7"] == 1
        assert summary["active_users_30"] == 2

    def test_anonymous_events_are_not_people(self):
        tree = quiet_tree()
        log(Kind.CARD_VIEW, tree=tree)
        log(Kind.LOGIN_FAILED)

        summary = activity_summary(today=TODAY)

        assert summary["active_users_30"] == 0
        assert summary["card_views_30"] == 1
        assert summary["failed_logins_7"] == 1

    def test_signups_count_new_accounts(self):
        ActivityEvent.objects.all().delete()
        person = quiet_user()
        log(Kind.SIGNUP, person, days_ago=3)
        log(Kind.SIGNUP, quiet_user(), days_ago=31)

        assert activity_summary(today=TODAY)["signups_30"] == 1

    def test_daily_series_splits_logins_from_interactions(self):
        person = quiet_user()
        tree = quiet_tree()
        log(Kind.LOGIN, person, days_ago=1)
        log(Kind.WATERING, person, tree, days_ago=1)
        log(Kind.CARE_TAKEN, person, tree, days_ago=1)
        log(Kind.CARD_VIEW, tree=tree, days_ago=1)  # neither

        daily = activity_summary(today=TODAY)["daily"]

        assert daily[-1] == {"day": TODAY, "logins": 0, "interactions": 0}
        assert daily[-2] == {"day": TODAY - timedelta(days=1), "logins": 1, "interactions": 2}

    def test_people_table_newest_activity_first(self):
        anna = quiet_user(display_name="Anna")
        jan = quiet_user(display_name="Jan")
        quiet_user(display_name="Nieaktywny")
        tree = quiet_tree()
        log(Kind.LOGIN, anna, days_ago=5)
        log(Kind.WATERING, anna, tree, days_ago=5)
        log(Kind.WATERING, anna, tree, days_ago=4)
        log(Kind.LOGIN, jan, days_ago=1)
        log(Kind.LOGIN, jan, days_ago=0)

        people = activity_summary(today=TODAY)["people"]

        assert [row["user"] for row in people] == [jan, anna]
        assert (people[0]["logins_30"], people[0]["interactions_30"]) == (2, 0)
        assert (people[1]["logins_30"], people[1]["interactions_30"]) == (1, 2)
        assert people[1]["last_seen"] == at(4)

    def test_query_count_does_not_grow_with_people(self, django_assert_max_num_queries):
        tree = quiet_tree()
        for _ in range(15):
            person = quiet_user()
            log(Kind.LOGIN, person)
            log(Kind.WATERING, person, tree)

        with django_assert_max_num_queries(10):
            summary = activity_summary(today=TODAY)
            [row["user"].display_name for row in summary["people"]]
