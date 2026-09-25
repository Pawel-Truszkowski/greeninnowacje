"""`recompute_statuses` — the 07:00 cron job (spec §6). Written before the code.

Runs the drought algorithm over every active tree. Two things matter beyond correctness:
the work per tree must not turn into a query per tree, and one gap in a locality's
weather must produce one warning, not one per tree standing there.
"""

import logging
from datetime import timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from core.models import load_drought_config
from factories import LocalityFactory, TreeFactory, UserFactory
from trees.models import Tree
from trees.services import recompute_all
from trees.tests.factories import water
from weather.models import WeatherDaily

pytestmark = pytest.mark.django_db


def old_tree(**kwargs):
    """Planted and registered long ago, so the registration grace period is over."""
    long_ago = timezone.now() - timedelta(days=200)
    return TreeFactory(planted_on=long_ago.date(), created_at=long_ago, **kwargs)


def fill_window(locality, mm="0.0", skip=()):
    yesterday = timezone.localdate() - timedelta(days=1)
    for offset in range(load_drought_config().rain_window_days):
        if offset not in skip:
            WeatherDaily.objects.create(
                locality=locality, day=yesterday - timedelta(days=offset), precip_mm=Decimal(mm)
            )


def run(*args):
    out = StringIO()
    call_command("recompute_statuses", *args, stdout=out, stderr=StringIO())
    return out.getvalue()


@pytest.fixture
def locality():
    return LocalityFactory(name="Sierpc")


@pytest.fixture
def dry_trees(locality):
    """Three trees with no rain and an old watering — a textbook drought."""
    user = UserFactory()
    trees = [old_tree(locality=locality, status=Tree.Status.OK) for _ in range(3)]
    for tree in trees:
        water(tree, user, days_ago=30)
    fill_window(locality)
    return trees


class TestRecomputeAll:
    def test_drought_turns_trees_urgent(self, dry_trees):
        result = recompute_all()

        assert result.checked == 3
        assert result.changed == 3
        assert result.counts == {"URGENT": 3}
        assert set(Tree.objects.values_list("status", flat=True)) == {Tree.Status.URGENT}

    def test_rain_above_the_threshold_turns_trees_ok(self, locality):
        config = load_drought_config()
        trees = [old_tree(locality=locality, status=Tree.Status.URGENT) for _ in range(2)]
        fill_window(locality, mm=str(config.rain_threshold_mm))

        result = recompute_all()

        assert result.counts == {"OK": 2}
        assert {tree.pk for tree in trees} == set(
            Tree.objects.filter(status=Tree.Status.OK).values_list("pk", flat=True)
        )

    def test_second_run_changes_nothing(self, dry_trees):
        recompute_all()

        result = recompute_all()

        assert result.checked == 3 and result.changed == 0

    def test_archived_trees_are_left_alone(self, locality, dry_trees):
        archived = old_tree(
            locality=locality, lifecycle=Tree.Lifecycle.ARCHIVED, status=Tree.Status.OK
        )

        result = recompute_all()

        archived.refresh_from_db()
        assert result.checked == 3
        assert archived.status == Tree.Status.OK

    def test_locality_narrows_the_run(self, dry_trees):
        other = LocalityFactory(name="Studzieniec")
        elsewhere = old_tree(locality=other, status=Tree.Status.OK)
        fill_window(other)

        recompute_all(locality_id=dry_trees[0].locality_id)

        elsewhere.refresh_from_db()
        assert elsewhere.status == Tree.Status.OK

    def test_dry_run_reports_without_saving(self, dry_trees):
        result = recompute_all(save=False)

        assert result.changed == 3
        assert set(Tree.objects.values_list("status", flat=True)) == {Tree.Status.OK}

    def test_empty_database(self):
        assert recompute_all() == recompute_all()  # no trees, no crash


class TestEfficiency:
    def test_query_count_does_not_grow_with_the_number_of_trees(
        self, locality, django_assert_num_queries
    ):
        user = UserFactory()
        fill_window(locality)
        for _ in range(3):
            water(old_tree(locality=locality), user, days_ago=30)
        with CaptureQueriesContext(connection) as captured:
            recompute_all()
        baseline = len(captured.captured_queries)

        for _ in range(9):
            water(old_tree(locality=locality), user, days_ago=30)
        with django_assert_num_queries(baseline):
            recompute_all()


class TestIncompleteWeatherLogging:
    def test_one_warning_per_locality_not_per_tree(self, locality, caplog):
        for _ in range(4):
            old_tree(locality=locality)
        fill_window(locality, skip={1})

        with caplog.at_level(logging.WARNING, logger="trees.services"):
            recompute_all()

        warnings = [line for line in caplog.text.splitlines() if "Niepełne dane" in line]
        assert len(warnings) == 1


class TestCommand:
    def test_prints_a_summary(self, dry_trees):
        output = run()

        assert "3" in output
        assert "URGENT" in output

    def test_dry_run_option(self, dry_trees):
        output = run("--dry-run")

        assert set(Tree.objects.values_list("status", flat=True)) == {Tree.Status.OK}
        assert output.strip()

    def test_locality_option(self, dry_trees):
        other = LocalityFactory(name="Studzieniec")
        elsewhere = old_tree(locality=other, status=Tree.Status.OK)
        fill_window(other)

        run("--locality", str(dry_trees[0].locality_id))

        elsewhere.refresh_from_db()
        assert elsewhere.status == Tree.Status.OK

    def test_empty_database_is_not_an_error(self):
        assert run().strip()
