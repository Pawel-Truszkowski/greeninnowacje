from decimal import Decimal

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.models import User
from core.models import Config, DroughtConfig, load_drought_config
from trees.models import Assignment, Tree, Watering
from weather.models import WeatherDaily

pytestmark = pytest.mark.django_db


def test_default_thresholds_seeded_by_migration():
    assert load_drought_config() == DroughtConfig(
        rain_window_days=5, rain_threshold_mm=Decimal("10"), days_soon=3, days_urgent=5
    )


def test_thresholds_read_from_table():
    Config.objects.filter(key="DAYS_URGENT").update(value="7")
    assert load_drought_config().days_urgent == 7


def test_seed_demo_is_idempotent(settings):
    settings.DEBUG = True
    call_command("seed_demo", password="haslo-demo-1234")
    counts = (Tree.objects.count(), Watering.objects.count(), Assignment.objects.count())
    call_command("seed_demo", password="haslo-demo-1234")

    assert counts == (14, 31, 9)
    assert (Tree.objects.count(), Watering.objects.count(), Assignment.objects.count()) == counts
    assert WeatherDaily.objects.count() == 28
    assert User.objects.get(email="admin@przyklad.pl").is_app_admin


def test_seed_demo_refuses_without_debug(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command("seed_demo")
