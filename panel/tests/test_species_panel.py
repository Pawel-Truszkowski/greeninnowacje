"""Species guides in the admin panel (Baza wiedzy, step 2).

What matters most: whatever an editor uploads — a 2 MB PNG straight from a chat window,
a phone photo — leaves the form as a JPEG of a known size, because the public view serves
every guide image as `image/jpeg` and the card grid expects one shape.
"""

import io

import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from accounts.models import User
from education.models import SpeciesGuide
from factories import UserFactory
from trees.forms import OTHER_SPECIES
from trees.models import TreeSpecies

pytestmark = pytest.mark.django_db

LIST = reverse("panel:species")
ADD = reverse("panel:add-species")


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


@pytest.fixture
def admin(client):
    person = UserFactory(role=User.Role.ADMIN)
    client.force_login(person)
    return person


def image(name="infografika.png", size=(1448, 1086), fmt="PNG"):
    buffer = io.BytesIO()
    Image.new("RGBA" if fmt == "PNG" else "RGB", size, "green").save(buffer, fmt)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=f"image/{fmt.lower()}")


def form_data(**overrides):
    data = {
        "species": "Jarząb pospolity",  # in the catalogue, no guide yet
        "species_other": "",
        "latin_name": "Sorbus aucuparia",
        "summary": "Drzewo o czerwonych owocach.",
        "traits": "Owoce dla ptaków | Jesienią przyciąga kosy i drozdy.",
        "params": "Docelowa wielkość | średnie",
        "plant_where": "parki",
        "dislikes": "zalewania",
        "position": "90",
        "is_published": "on",
        "infographic": image(),
        "photo": image("drzewo.jpg", size=(1200, 900), fmt="JPEG"),
    }
    data.update(overrides)
    return {key: value for key, value in data.items() if value is not None}


def opened(field_file):
    with default_storage.open(field_file.name) as fh:
        img = Image.open(fh)
        return img.format, img.size


class TestList:
    def test_lists_every_guide_hidden_ones_too(self, client, admin):
        SpeciesGuide.objects.filter(slug="olsza-czarna").update(is_published=False)

        html = client.get(LIST).content.decode()

        for guide in SpeciesGuide.objects.all():
            assert reverse("panel:edit-species", args=[guide.pk]) in html
        assert "Ukryty" in html

    def test_panel_has_a_species_tab(self, client, admin):
        html = client.get(reverse("panel:dashboard")).content.decode()

        assert f'href="{LIST}"' in html


class TestAdd:
    def test_png_infographic_and_photo_are_stored_as_jpeg(self, client, admin):
        response = client.post(ADD, form_data())

        assert response.status_code == 302
        guide = SpeciesGuide.objects.get(slug="jarzab-pospolity")
        assert guide.name == "Jarząb pospolity"
        assert opened(guide.infographic) == ("JPEG", (1448, 1086))
        assert opened(guide.photo) == ("JPEG", (400, 500))
        assert (guide.photo_width, guide.photo_height) == (400, 500)

    def test_new_guide_appears_in_the_knowledge_base(self, client, admin):
        client.post(ADD, form_data())

        html = client.get(reverse("education:index")).content.decode()

        assert reverse("education:species", args=["jarzab-pospolity"]) in html

    def test_typed_species_joins_the_catalogue(self, client, admin):
        client.post(ADD, form_data(species=OTHER_SPECIES, species_other="Buk zwyczajny"))

        guide = SpeciesGuide.objects.get(slug="buk-zwyczajny")
        assert guide.species == TreeSpecies.objects.get(name="Buk zwyczajny")

    def test_choices_leave_out_species_that_have_a_guide(self, client, admin):
        form = client.get(ADD).context["form"]
        names = [value for value, _ in form.fields["species"].choices]

        assert "Jarząb pospolity" in names
        assert "Lipa drobnolistna" not in names

    def test_typed_species_that_has_a_guide_is_refused(self, client, admin):
        data = form_data(species=OTHER_SPECIES, species_other="lipa  DROBNOLISTNA")

        response = client.post(ADD, data)

        assert response.status_code == 200
        assert "ma już opis" in response.content.decode()
        assert SpeciesGuide.objects.count() == 8

    def test_images_are_required(self, client, admin):
        response = client.post(ADD, form_data(infographic=None, photo=None))

        form = response.context["form"]
        assert "infographic" in form.errors and "photo" in form.errors

    def test_file_that_is_not_an_image_is_refused(self, client, admin):
        fake = SimpleUploadedFile("infografika.png", b"<script>alert(1)</script>")

        response = client.post(ADD, form_data(infographic=fake))

        assert response.context["form"].errors["infographic"] == ["Nie udało się odczytać zdjęcia."]
        assert not SpeciesGuide.objects.filter(slug="jarzab-pospolity").exists()
        assert not TreeSpecies.objects.filter(name__iexact="Jarzab pospolity").exists()

    def test_position_defaults_to_the_end(self, client, admin):
        form = client.get(ADD).context["form"]

        assert form.initial["position"] == 90  # seeded at 10, 20, …, 80


class TestEdit:
    def url(self, slug="klon-polny"):
        return reverse("panel:edit-species", args=[SpeciesGuide.objects.get(slug=slug).pk])

    def test_text_changes_without_new_files(self, client, admin):
        guide = SpeciesGuide.objects.get(slug="klon-polny")
        files = (guide.infographic.name, guide.photo.name)

        response = client.post(
            self.url(),
            form_data(species="Klon polny", summary="Nowy opis.", infographic=None, photo=None),
        )

        assert response.status_code == 302
        # A fresh query, not refresh_from_db(): that re-reads image sizes from files, and the
        # seeded ones are not in this test's MEDIA_ROOT.
        guide = SpeciesGuide.objects.get(slug="klon-polny")
        assert guide.summary == "Nowy opis."
        assert (guide.infographic.name, guide.photo.name) == files

    def test_own_species_stays_selectable(self, client, admin):
        form = client.get(self.url()).context["form"]

        assert form.initial["species"] == "Klon polny"
        assert "Klon polny" in [value for value, _ in form.fields["species"].choices]

    def test_cannot_take_a_species_another_guide_has(self, client, admin):
        data = form_data(species=OTHER_SPECIES, species_other="Lipa drobnolistna")

        response = client.post(self.url(), data | {"infographic": "", "photo": ""})

        assert response.status_code == 200
        assert SpeciesGuide.objects.get(slug="klon-polny").name == "Klon polny"

    def test_slug_does_not_follow_a_new_species(self, client, admin):
        data = form_data(species="Jarząb pospolity", infographic=None, photo=None)

        client.post(self.url(), data)

        guide = SpeciesGuide.objects.get(slug="klon-polny")
        assert guide.name == "Jarząb pospolity"

    def test_new_infographic_replaces_the_file(
        self, client, admin, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            client.post(self.url(), form_data(species="Klon polny", photo=None))

        guide = SpeciesGuide.objects.get(slug="klon-polny")
        assert guide.infographic.name.startswith("gatunki/klon-polny")
        assert opened(guide.infographic) == ("JPEG", (1448, 1086))


class TestPublishing:
    def test_toggle_hides_and_shows_again(self, client, admin):
        guide = SpeciesGuide.objects.get(slug="grab-pospolity")
        url = reverse("panel:toggle-species", args=[guide.pk])

        client.post(url)
        assert client.get(reverse("education:species", args=[guide.slug])).status_code == 404

        client.post(url)
        assert client.get(reverse("education:species", args=[guide.slug])).status_code == 200

    def test_hidden_guide_has_a_preview_in_the_panel_only(self, client, admin):
        client.post(ADD, form_data(is_published=None))
        guide = SpeciesGuide.objects.get(slug="jarzab-pospolity")

        preview = client.get(reverse("panel:species-image", args=[guide.pk, "infografika"]))
        public = client.get(reverse("education:species-image", args=[guide.slug, "infografika"]))

        assert preview.status_code == 200
        assert preview["Content-Type"] == "image/jpeg"
        assert public.status_code == 404
