"""Storing and removing tree photos (Etap 2). Written before the implementation.

Two rules carry the weight: only people with a real connection to the tree may add a photo,
because nothing moderates the content, and the public card must never learn photos exist —
the same reason it has never carried volunteer names (spec §4).
"""

import io

import pytest
from PIL import Image

from factories import TreeFactory, UserFactory
from trees.images import InvalidImage
from trees.models import TreePhoto
from trees.selectors import extended_tree_card, public_tree_card
from trees.services import (
    MAX_PHOTOS_PER_TREE,
    PhotoNotAllowed,
    add_photo,
    can_manage_photos,
    delete_photo,
)
from trees.tests.factories import assign

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


def upload(name="zdjecie.jpg", size=(900, 600), colour="green"):
    """A photo as a view would receive it."""
    buffer = io.BytesIO()
    Image.new("RGB", size, colour).save(buffer, "JPEG")
    data = buffer.getvalue()

    handed_over = io.BytesIO(data)
    handed_over.size = len(data)
    handed_over.name = name
    return handed_over


@pytest.fixture
def caretaker_tree():
    """A tree with an active caretaker, plus the volunteer who registered it."""
    owner = UserFactory(display_name="Zakładający")
    tree = TreeFactory(created_by=owner)
    caretaker = UserFactory(display_name="Opiekun")
    assign(tree, caretaker)
    return tree, owner, caretaker


class TestWhoMayAddPhotos:
    def test_caretaker_may(self, caretaker_tree):
        tree, _, caretaker = caretaker_tree

        assert can_manage_photos(tree, caretaker) is True

    def test_registering_volunteer_may(self, caretaker_tree):
        tree, owner, _ = caretaker_tree

        assert can_manage_photos(tree, owner) is True

    def test_admin_may(self, caretaker_tree):
        tree, _, _ = caretaker_tree

        assert can_manage_photos(tree, UserFactory(role="admin")) is True

    def test_unrelated_volunteer_may_not(self, caretaker_tree):
        """Watering is open to anyone logged in; photos are not, because nobody moderates."""
        tree, _, _ = caretaker_tree

        assert can_manage_photos(tree, UserFactory()) is False

    def test_former_caretaker_may_not(self, caretaker_tree):
        tree, _, caretaker = caretaker_tree
        from django.utils import timezone

        tree.assignments.filter(user=caretaker).update(ended_at=timezone.now())

        assert can_manage_photos(tree, caretaker) is False


class TestAddPhoto:
    def test_stores_a_processed_photo(self, caretaker_tree):
        tree, _, caretaker = caretaker_tree

        photo = add_photo(tree, caretaker, upload())

        assert photo.tree == tree
        assert photo.uploaded_by == caretaker
        assert photo.image.name.endswith(".jpg")

    def test_dimensions_come_from_processing_not_from_the_client(self, caretaker_tree):
        """A 4000 px photo is stored downscaled, and the row must say the stored size."""
        tree, _, caretaker = caretaker_tree

        photo = add_photo(tree, caretaker, upload(size=(4000, 3000)))

        assert (photo.width, photo.height) == Image.open(photo.image.open()).size

    def test_file_really_lands_in_media_root(self, caretaker_tree, media_root):
        tree, _, caretaker = caretaker_tree

        photo = add_photo(tree, caretaker, upload())

        assert (media_root / photo.image.name).exists()

    def test_unrelated_volunteer_is_refused(self, caretaker_tree):
        tree, _, _ = caretaker_tree

        with pytest.raises(PhotoNotAllowed):
            add_photo(tree, UserFactory(), upload())

        assert not TreePhoto.objects.exists()

    def test_a_broken_file_is_rejected_by_the_image_layer(self, caretaker_tree):
        tree, _, caretaker = caretaker_tree
        junk = io.BytesIO(b"to nie jest obraz")
        junk.size, junk.name = 17, "notatka.jpg"

        with pytest.raises(InvalidImage):
            add_photo(tree, caretaker, junk)

        assert not TreePhoto.objects.exists()

    def test_limit_per_tree(self, caretaker_tree):
        tree, _, caretaker = caretaker_tree
        for _ in range(MAX_PHOTOS_PER_TREE):
            add_photo(tree, caretaker, upload())

        with pytest.raises(PhotoNotAllowed):
            add_photo(tree, caretaker, upload())

    def test_limit_counts_only_this_tree(self, caretaker_tree):
        tree, _, caretaker = caretaker_tree
        add_photo(tree, caretaker, upload())
        other = TreeFactory(created_by=caretaker)

        assert add_photo(other, caretaker, upload())


class TestDeletePhoto:
    def test_uploader_may_remove_their_own(self, caretaker_tree, media_root):
        tree, _, caretaker = caretaker_tree
        photo = add_photo(tree, caretaker, upload())
        path = media_root / photo.image.name

        delete_photo(photo, caretaker)

        assert not TreePhoto.objects.exists()
        assert not path.exists(), "Plik musi zniknąć razem z wierszem"

    def test_admin_may_remove_anything(self, caretaker_tree):
        """RODO: someone in the photo may ask for it, and they ask the administrator."""
        tree, _, caretaker = caretaker_tree
        photo = add_photo(tree, caretaker, upload())
        assert TreePhoto.objects.count() == 1, "Bez zapisanego zdjęcia test nic nie sprawdza"

        delete_photo(photo, UserFactory(role="admin"))

        assert not TreePhoto.objects.exists()

    def test_another_volunteer_may_not(self, caretaker_tree):
        tree, _, caretaker = caretaker_tree
        photo = add_photo(tree, caretaker, upload())

        with pytest.raises(PhotoNotAllowed):
            delete_photo(photo, UserFactory())

        assert TreePhoto.objects.count() == 1

    def test_removing_a_photo_leaves_the_tree_alone(self, caretaker_tree):
        """Photos are deleted outright; trees are only ever archived (spec §3)."""
        tree, _, caretaker = caretaker_tree
        photo = add_photo(tree, caretaker, upload())
        assert photo is not None, "Bez zapisanego zdjęcia test nic nie sprawdza"
        delete_photo(photo, caretaker)

        tree.refresh_from_db()
        assert tree.lifecycle == "active"


class TestCards:
    def test_public_card_says_nothing_about_photos(self, caretaker_tree):
        """The neighbour of the M1 "no personal data" test — and for the same reason."""
        tree, _, caretaker = caretaker_tree
        add_photo(tree, caretaker, upload())
        assert TreePhoto.objects.count() == 1, "Bez zapisanego zdjęcia test nic nie sprawdza"

        card = public_tree_card(tree)

        assert "photos" not in card
        assert not any("photo" in key for key in card)

    def test_logged_in_card_lists_photos_newest_first(self, caretaker_tree):
        tree, _, caretaker = caretaker_tree
        older = add_photo(tree, caretaker, upload())
        newer = add_photo(tree, caretaker, upload())
        TreePhoto.objects.filter(pk=older.pk).update(created_at="2026-01-01T10:00:00+01:00")

        photos = extended_tree_card(tree)["photos"]

        assert [photo.pk for photo in photos] == [newer.pk, older.pk]

    def test_logged_in_card_without_photos_is_an_empty_list(self, caretaker_tree):
        tree, _, _ = caretaker_tree

        assert extended_tree_card(tree)["photos"] == []

    def test_photos_do_not_cost_a_query_each(self, caretaker_tree, django_assert_num_queries):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        tree, _, caretaker = caretaker_tree
        for _ in range(2):
            add_photo(tree, caretaker, upload())
        assert TreePhoto.objects.count() == 2, "Bez zdjęć nie ma czego liczyć"
        with CaptureQueriesContext(connection) as captured:
            extended_tree_card(tree)
        baseline = len(captured.captured_queries)

        for _ in range(6):
            add_photo(tree, caretaker, upload())
        with django_assert_num_queries(baseline):
            extended_tree_card(tree)
