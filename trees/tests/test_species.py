"""Tree species catalogue: the list behind the registration form's dropdown.

Written before the implementation. The catalogue exists so that statistics per species
(spec §5.9) are not ruined by "Jabłoń" and "Jabłoń domowa" being typed as separate names;
`Tree.species` itself stays a text column, as the schema contract requires (spec §3).
"""

import pytest
from django.core.management import call_command
from django.db.utils import IntegrityError

from trees.models import Tree, TreeSpecies
from trees.selectors import active_species_names

pytestmark = pytest.mark.django_db

# The list the PoC offered (poc/rejestracja-drzewa.html).
POC_SPECIES = [
    "Brzoza brodawkowata",
    "Dąb bezszypułkowy",
    "Dąb szypułkowy",
    "Grab pospolity",
    "Jarząb pospolity",
    "Klon polny",
    "Klon zwyczajny",
    "Lipa drobnolistna",
    "Lipa szerokolistna",
    "Wiśnia ptasia",
]


class TestSeededCatalogue:
    def test_migration_seeds_the_poc_list(self):
        names = set(TreeSpecies.objects.values_list("name", flat=True))

        assert set(POC_SPECIES) <= names

    def test_seeded_species_are_active(self):
        assert TreeSpecies.objects.filter(is_active=False).count() == 0

    def test_demo_data_species_are_all_in_the_catalogue(self, settings):
        """Demo trees include species outside the PoC list (e.g. "Grusza – Konferencja")."""
        settings.DEBUG = True
        call_command("seed_demo", password="haslo-demo-1234")

        used = set(Tree.objects.values_list("species", flat=True))
        known = set(TreeSpecies.objects.values_list("name", flat=True))

        assert used <= known


class TestCatalogueModel:
    def test_minimal_species(self):
        species = TreeSpecies.objects.create(name="Morela")

        assert species.is_active is True
        assert str(species) == "Morela"

    def test_names_are_unique_regardless_of_case(self):
        TreeSpecies.objects.create(name="Grusza Konferencja")

        with pytest.raises(IntegrityError):
            TreeSpecies.objects.create(name="grusza konferencja")

    def test_ordered_by_name(self, empty_species_catalogue):
        TreeSpecies.objects.create(name="Wierzba")
        TreeSpecies.objects.create(name="Buk")

        assert list(TreeSpecies.objects.values_list("name", flat=True)) == ["Buk", "Wierzba"]


class TestActiveSpeciesNames:
    def test_returns_sorted_names(self, empty_species_catalogue):
        TreeSpecies.objects.create(name="Wierzba")
        TreeSpecies.objects.create(name="Buk")

        assert active_species_names() == ["Buk", "Wierzba"]

    def test_skips_retired_species(self, empty_species_catalogue):
        TreeSpecies.objects.create(name="Buk")
        TreeSpecies.objects.create(name="Topola", is_active=False)

        assert active_species_names() == ["Buk"]

    def test_empty_catalogue(self, empty_species_catalogue):

        assert active_species_names() == []


def test_tree_species_stays_free_text(db):
    """The catalogue feeds the dropdown; it does not replace Tree.species (spec §3)."""
    field = Tree._meta.get_field("species")

    assert field.get_internal_type() == "CharField"
    assert not field.is_relation
