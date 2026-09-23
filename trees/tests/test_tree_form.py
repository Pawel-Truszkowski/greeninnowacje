"""Validation of the registration form (spec §7: never trust client coordinates)."""

from datetime import timedelta

import pytest
from django.utils import timezone

from trees.forms import TreeRegistrationForm

pytestmark = pytest.mark.django_db


def form_data(**overrides):
    return TreeRegistrationForm(
        {
            "species": "Lipa drobnolistna",
            "planted_on": timezone.localdate().isoformat(),
            "planted_by": "Wolontariusze",
            "notes": "",
            "lat": "52.871000",
            "lng": "19.651000",
            "gps_accuracy_m": "4.2",
            "locality_name": "",
        }
        | overrides
    )


def test_minimal_valid_submission():
    assert form_data().is_valid()


def test_species_is_required():
    form = form_data(species="")
    assert not form.is_valid() and "species" in form.errors


def test_planting_date_cannot_be_in_the_future():
    tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
    form = form_data(planted_on=tomorrow)

    assert not form.is_valid()
    assert "przyszłości" in form.errors["planted_on"][0]


def test_coordinates_are_required():
    form = form_data(lat="", lng="")
    assert not form.is_valid()
    assert "Brak lokalizacji" in form.errors["__all__"][0]


@pytest.mark.parametrize(("lat", "lng"), [("48.85", "2.35"), ("0", "0"), ("52.52", "13.40")])
def test_coordinates_outside_poland_are_rejected(lat, lng):
    form = form_data(lat=lat, lng=lng)
    assert not form.is_valid()
    assert "spoza Polski" in form.errors["__all__"][0]


def test_registration_fields_exclude_locality_name():
    form = form_data(locality_name="Sierpc")
    assert form.is_valid()
    assert "locality_name" not in form.registration_fields()
    assert form.registration_fields()["species"] == "Lipa drobnolistna"
