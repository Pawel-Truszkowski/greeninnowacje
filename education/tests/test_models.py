"""SpeciesGuide: the one-item-per-line text fields and what the seed migration leaves behind."""

from pathlib import Path

import pytest
from django.core.files.storage import default_storage
from django.db.models.deletion import ProtectedError

from education.models import SpeciesGuide
from trees.models import TreeSpecies

pytestmark = pytest.mark.django_db

SEEDED = [
    "dab-szypulkowy",
    "dab-bezszypulkowy",
    "lipa-drobnolistna",
    "klon-zwyczajny",
    "klon-polny",
    "grab-pospolity",
    "brzoza-brodawkowata",
    "olsza-czarna",
]


def make_guide(**fields):
    species = TreeSpecies.objects.create(name=fields.pop("name", "Buk zwyczajny"))
    defaults = {
        "slug": "buk-zwyczajny",
        "latin_name": "Fagus sylvatica",
        "summary": "Opis.",
        "infographic": "gatunki/dab-szypulkowy.jpg",
        "photo": "gatunki/dab-szypulkowy-foto.jpg",
    }
    return SpeciesGuide.objects.create(species=species, **{**defaults, **fields})


class TestTextFields:
    def test_lines_skip_blanks_and_dashes(self):
        guide = make_guide(plant_where="parki\n\n  —  \nogrody  \n-")

        assert guide.plant_where_list == ["parki", "ogrody"]

    def test_traits_split_title_and_description(self):
        guide = make_guide(traits="Lubi wodę | Rośnie nad rzekami.\nDługowieczny")

        assert guide.trait_list == [("Lubi wodę", "Rośnie nad rzekami."), ("Długowieczny", "")]

    def test_param_without_value_is_left_out(self):
        # The birch infographic prints "—" in four cells; the text version must not show them.
        guide = make_guide(params="Docelowa wielkość | duże\nSzerokość korony | —\nWoda |")

        assert guide.param_list == [("Docelowa wielkość", "duże")]

    def test_name_comes_from_the_catalogue(self):
        guide = make_guide(name="Buk zwyczajny")

        assert guide.name == str(guide) == "Buk zwyczajny"


class TestSeed:
    def test_eight_guides_in_the_mentors_order(self):
        assert list(SpeciesGuide.objects.values_list("slug", flat=True)) == SEEDED

    def test_every_guide_is_published_with_both_images(self):
        for guide in SpeciesGuide.objects.all():
            assert guide.is_published
            assert default_storage.exists(guide.infographic.name), guide.slug
            assert default_storage.exists(guide.photo.name), guide.slug
            assert (guide.infographic_width, guide.infographic_height) == (1448, 1086)
            assert (guide.photo_width, guide.photo_height) == (400, 500)

    def test_every_guide_has_a_text_version(self):
        for guide in SpeciesGuide.objects.all():
            assert guide.summary and guide.trait_list and guide.param_list, guide.slug
            assert guide.plant_where_list and guide.dislike_list, guide.slug

    def test_seed_files_ship_with_the_code(self):
        # The migration copies them into media on the server; without them a deploy fails.
        seed_dir = Path(__file__).resolve().parent.parent / "seed" / "gatunki"
        for slug in SEEDED:
            assert (seed_dir / f"{slug}.jpg").is_file()
            assert (seed_dir / f"{slug}-foto.jpg").is_file()

    def test_black_alder_joins_the_registration_catalogue(self):
        assert TreeSpecies.objects.filter(name="Olsza czarna", is_active=True).exists()

    def test_species_with_a_guide_cannot_be_deleted(self):
        with pytest.raises(ProtectedError):
            TreeSpecies.objects.get(name="Olsza czarna").delete()
