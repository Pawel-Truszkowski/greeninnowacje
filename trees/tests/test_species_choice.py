"""Species dropdown in the registration form (PoC: list + "Inny (wpiszę ręcznie)").

Written before the implementation. The point of the list is data quality — "Jabłoń" and
"Jabłoń domowa" typed as separate names ruin the per-species statistics (spec §5.9) —
while the "Inny" escape hatch keeps a volunteer with an unusual tree from getting stuck.
A name entered that way is stored on the tree but NOT added to the catalogue: extending
the list is the administrator's decision.
"""

import pytest
from django.urls import reverse
from django.utils import timezone

from factories import UserFactory
from trees.forms import OTHER_SPECIES, TreeRegistrationForm
from trees.models import Tree, TreeSpecies

pytestmark = pytest.mark.django_db

CREATE_URL = reverse("trees-api:create")
PAGE_URL = reverse("trees:register")


@pytest.fixture(autouse=True)
def no_geocoder(monkeypatch):
    monkeypatch.setattr("trees.services.reverse_locality", lambda lat, lng: "Sierpc")


@pytest.fixture
def catalogue():
    TreeSpecies.objects.all().delete()
    return [
        TreeSpecies.objects.create(name="Dąb szypułkowy"),
        TreeSpecies.objects.create(name="Lipa drobnolistna"),
    ]


@pytest.fixture
def volunteer(client):
    user = UserFactory()
    client.force_login(user)
    return user


def form_data(**overrides):
    return {
        "species": "Lipa drobnolistna",
        "species_other": "",
        "planted_on": timezone.localdate().isoformat(),
        "planted_by": "Wolontariusze",
        "notes": "",
        "lat": "52.871000",
        "lng": "19.651000",
        "gps_accuracy_m": "4.2",
        "locality_name": "",
    } | overrides


class TestChoices:
    def test_offers_catalogue_species_and_the_other_option(self, catalogue):
        choices = dict(TreeRegistrationForm().fields["species"].choices)

        assert "Dąb szypułkowy" in choices
        assert "Lipa drobnolistna" in choices
        assert choices[OTHER_SPECIES].startswith("Inny")

    def test_has_an_empty_prompt(self, catalogue):
        values = [value for value, _ in TreeRegistrationForm().fields["species"].choices]

        assert values[0] == ""

    def test_retired_species_are_not_offered(self, catalogue):
        TreeSpecies.objects.filter(name="Dąb szypułkowy").update(is_active=False)

        choices = dict(TreeRegistrationForm().fields["species"].choices)

        assert "Dąb szypułkowy" not in choices

    def test_choices_follow_the_catalogue(self, catalogue):
        """Built per form instance, so an admin's change is visible without a restart."""
        TreeSpecies.objects.create(name="Morela")

        assert "Morela" in dict(TreeRegistrationForm().fields["species"].choices)


class TestValidation:
    def test_species_from_the_catalogue_is_accepted(self, catalogue):
        form = TreeRegistrationForm(form_data())

        assert form.is_valid(), form.errors
        assert form.cleaned_data["species"] == "Lipa drobnolistna"

    def test_species_outside_the_catalogue_is_rejected(self, catalogue):
        form = TreeRegistrationForm(form_data(species="Baobab afrykański"))

        assert not form.is_valid()
        assert "species" in form.errors

    def test_retired_species_is_rejected(self, catalogue):
        TreeSpecies.objects.filter(name="Lipa drobnolistna").update(is_active=False)

        assert not TreeRegistrationForm(form_data()).is_valid()

    def test_other_with_a_name(self, catalogue):
        form = TreeRegistrationForm(
            form_data(species=OTHER_SPECIES, species_other="  Miłorząb dwuklapowy  ")
        )

        assert form.is_valid(), form.errors
        assert form.cleaned_data["species"] == "Miłorząb dwuklapowy"

    @pytest.mark.parametrize("value", ["", "   "])
    def test_other_without_a_name(self, catalogue, value):
        form = TreeRegistrationForm(form_data(species=OTHER_SPECIES, species_other=value))

        assert not form.is_valid()
        assert "species_other" in form.errors

    def test_species_is_still_required(self, catalogue):
        form = TreeRegistrationForm(form_data(species=""))

        assert not form.is_valid()
        assert "species" in form.errors


class TestRegistrationEndpoints:
    def test_api_rejects_species_outside_the_catalogue(self, client, volunteer, catalogue):
        """The dropdown is a hint for humans; the server is what actually enforces it."""
        response = client.post(
            CREATE_URL, form_data(species="Baobab afrykański"), content_type="application/json"
        )

        assert response.status_code == 400
        assert "species" in response.json()["errors"]
        assert not Tree.objects.exists()

    def test_api_accepts_other(self, client, volunteer, catalogue):
        response = client.post(
            CREATE_URL,
            form_data(species=OTHER_SPECIES, species_other="Miłorząb dwuklapowy"),
            content_type="application/json",
        )

        assert response.status_code == 201
        assert Tree.objects.get().species == "Miłorząb dwuklapowy"

    def test_other_does_not_grow_the_catalogue(self, client, volunteer, catalogue):
        """Extending the list stays an administrator's decision."""
        client.post(
            CREATE_URL,
            form_data(species=OTHER_SPECIES, species_other="Miłorząb dwuklapowy"),
            content_type="application/json",
        )

        assert TreeSpecies.objects.count() == len(catalogue)
        assert not TreeSpecies.objects.filter(name__iexact="Miłorząb dwuklapowy").exists()

    def test_page_renders_the_dropdown(self, client, volunteer, catalogue):
        content = client.get(PAGE_URL).content.decode()

        assert "<select" in content
        assert "Lipa drobnolistna" in content
        assert "Inny" in content
        assert 'name="species_other"' in content

    def test_page_registers_a_tree_from_the_list(self, client, volunteer, catalogue):
        client.post(PAGE_URL, form_data())

        assert Tree.objects.get().species == "Lipa drobnolistna"


def test_retiring_a_species_keeps_existing_trees_intact(client, volunteer, catalogue):
    """Trees keep the name recorded at registration — that is why species is text."""
    client.post(PAGE_URL, form_data())
    TreeSpecies.objects.filter(name="Lipa drobnolistna").update(is_active=False)

    tree = Tree.objects.get()
    card = client.get(reverse("trees:card", kwargs={"tree_id": tree.pk}))

    assert tree.species == "Lipa drobnolistna"
    assert card.status_code == 200
    assert "Lipa drobnolistna" in card.content.decode()
