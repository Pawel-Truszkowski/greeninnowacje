"""The drought window ends yesterday, not today. Written before the change.

Today's rainfall is never stored (it is still a forecast), so a window reaching into
today would report a missing day on every single run — and a warning that always fires
is a warning nobody reads. Finished days only: then "incomplete data" means a real gap in
what Open-Meteo gave us (spec §5.1, §6.2).
"""

import logging
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.models import load_drought_config
from factories import TreeFactory
from trees.models import Tree
from trees.selectors import weather_series
from trees.services import recompute_tree_status
from weather.models import WeatherDaily

pytestmark = pytest.mark.django_db


@pytest.fixture
def tree():
    # Registered long ago as well: a freshly added tree is held back from URGENT by the
    # registration grace period (trees/status.py), which would mask what we test here.
    long_ago = timezone.now() - timedelta(days=200)
    return TreeFactory(planted_on=long_ago.date(), created_at=long_ago)


def rain(locality, day, mm):
    return WeatherDaily.objects.create(locality=locality, day=day, precip_mm=Decimal(mm))


def fill_window(locality, mm="0.0", days=None, skip=()):
    """Readings for every finished day of the drought window, minus `skip` offsets."""
    days = days or load_drought_config().rain_window_days
    yesterday = timezone.localdate() - timedelta(days=1)
    for offset in range(days):
        if offset not in skip:
            rain(locality, yesterday - timedelta(days=offset), mm)


class TestSeries:
    def test_ends_yesterday(self, tree):
        series = weather_series(tree.locality_id, days=5)

        assert series[-1]["day"] == timezone.localdate() - timedelta(days=1)
        assert len(series) == 5

    def test_today_is_not_part_of_the_window(self, tree):
        rain(tree.locality, timezone.localdate(), "20.0")

        series = weather_series(tree.locality_id, days=5)

        assert timezone.localdate() not in [day["day"] for day in series]

    def test_end_day_can_be_given_explicitly(self, tree):
        end_day = timezone.localdate() - timedelta(days=10)

        series = weather_series(tree.locality_id, days=3, end_day=end_day)

        assert [day["day"] for day in series] == [
            end_day - timedelta(days=2),
            end_day - timedelta(days=1),
            end_day,
        ]


class TestIncompleteDataWarning:
    def test_no_warning_when_every_finished_day_is_known(self, tree, caplog):
        fill_window(tree.locality)

        with caplog.at_level(logging.WARNING, logger="trees.services"):
            recompute_tree_status(tree)

        assert "Niepełne dane pogodowe" not in caplog.text

    def test_warning_names_a_real_gap(self, tree, caplog):
        fill_window(tree.locality, skip={2})
        missing = timezone.localdate() - timedelta(days=3)

        with caplog.at_level(logging.WARNING, logger="trees.services"):
            recompute_tree_status(tree)

        assert "Niepełne dane pogodowe" in caplog.text
        assert missing.isoformat() in caplog.text


class TestStatusUsesFinishedDays:
    def test_yesterdays_downpour_counts(self, tree):
        """Rain above the threshold yesterday means the tree is fine today."""
        config = load_drought_config()
        fill_window(tree.locality)
        WeatherDaily.objects.filter(day=timezone.localdate() - timedelta(days=1)).update(
            precip_mm=config.rain_threshold_mm
        )

        assert recompute_tree_status(tree) == Tree.Status.OK

    def test_todays_forecast_would_not_count(self, tree):
        """Even a big number stored for today must not rescue a dry tree."""
        fill_window(tree.locality)
        rain(tree.locality, timezone.localdate(), "50.0")

        assert recompute_tree_status(tree) == Tree.Status.URGENT
