"""Writing species guides: the slug, the catalogue link and the files left on disk."""

import io

import pytest
from django.core.files.storage import default_storage
from PIL import Image

from education.models import SpeciesGuide
from education.services import CARD_PHOTO_SIZE, catalogue_species, save_guide, species_slug
from trees.images import process_upload
from trees.models import TreeSpecies

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


def processed(size=(1200, 900), **options):
    buffer = io.BytesIO()
    Image.new("RGB", size, "green").save(buffer, "PNG")
    buffer.seek(0)
    buffer.size = len(buffer.getvalue())
    return process_upload(buffer, **options)


def new_guide(name="Buk zwyczajny"):
    guide = SpeciesGuide(latin_name="Fagus sylvatica", summary="Opis.")
    return save_guide(
        guide,
        name,
        infographic=processed(),
        photo=processed(fit=CARD_PHOTO_SIZE),
    )


class TestSlug:
    @pytest.mark.parametrize(
        ("name", "slug"),
        [
            # Django's slugify alone drops "ł": "wiaz-szypukowy".
            ("Wiąz szypułkowy", "wiaz-szypulkowy"),
            ("Wiśnia ptasia", "wisnia-ptasia"),
            ("ŁOZA  żółta", "loza-zolta"),
        ],
    )
    def test_polish_letters_become_ascii(self, name, slug):
        assert species_slug(name) == slug

    def test_taken_slug_gets_a_number(self):
        # "dab-szypulkowy" is seeded.
        assert species_slug("Dąb Szypułkowy") == "dab-szypulkowy-2"


class TestCatalogue:
    def test_existing_species_is_found_whatever_the_case(self):
        assert catalogue_species("jarząb  POSPOLITY").name == "Jarząb pospolity"

    def test_new_species_joins_the_catalogue(self):
        species = catalogue_species("  Buk   zwyczajny ")

        assert species.name == "Buk zwyczajny"
        assert TreeSpecies.objects.filter(name="Buk zwyczajny", is_active=True).exists()


class TestSaveGuide:
    def test_new_guide_gets_slug_files_and_sizes(self):
        guide = new_guide()

        assert guide.slug == "buk-zwyczajny"
        assert guide.infographic.name.startswith("gatunki/buk-zwyczajny")
        assert guide.photo.name.startswith("gatunki/buk-zwyczajny-foto")
        assert (guide.infographic_width, guide.infographic_height) == (1200, 900)
        assert (guide.photo_width, guide.photo_height) == CARD_PHOTO_SIZE
        assert default_storage.exists(guide.infographic.name)

    def test_slug_stays_when_the_species_changes(self):
        guide = new_guide()

        save_guide(guide, "Buk pospolity")

        guide.refresh_from_db()
        assert guide.name == "Buk pospolity"
        assert guide.slug == "buk-zwyczajny"

    def test_replaced_image_is_deleted_after_commit(self, django_capture_on_commit_callbacks):
        guide = new_guide()
        old = guide.infographic.name

        with django_capture_on_commit_callbacks(execute=True):
            save_guide(guide, guide.name, infographic=processed(size=(800, 600)))

        assert not default_storage.exists(old)
        assert default_storage.exists(guide.infographic.name)
        assert guide.infographic_width == 800

    def test_without_new_files_the_current_ones_stay(self, django_capture_on_commit_callbacks):
        guide = new_guide()
        files = (guide.infographic.name, guide.photo.name)

        with django_capture_on_commit_callbacks(execute=True):
            guide.summary = "Nowy opis."
            save_guide(guide, guide.name)

        guide.refresh_from_db()
        assert (guide.infographic.name, guide.photo.name) == files
        assert all(default_storage.exists(name) for name in files)
