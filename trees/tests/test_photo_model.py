"""The `TreePhoto` model (Etap 2). Written before the implementation.

`MEDIA_ROOT` points at a temporary directory, so a test run never writes photos into the
working copy. The real setting arrives with the storage cycle.
"""

import uuid
from datetime import timedelta

import pytest
from django.core.files.base import ContentFile
from django.db.models import PROTECT, ProtectedError
from django.utils import timezone

from factories import TreeFactory, UserFactory
from trees.models import TreePhoto

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


def photo(tree=None, user=None, name="zdjecie.jpg", content=b"udawany-jpeg"):
    return TreePhoto.objects.create(
        tree=tree or TreeFactory(),
        uploaded_by=user or UserFactory(),
        image=ContentFile(content, name=name),
    )


class TestSchema:
    def test_table_name_and_polish_labels(self):
        meta = TreePhoto._meta

        assert meta.db_table == "tree_photos"
        assert meta.verbose_name and meta.verbose_name[0].islower()

    def test_primary_key_is_a_uuid(self):
        assert isinstance(photo().pk, uuid.UUID)

    def test_newest_first(self):
        tree = TreeFactory()
        older, newer = photo(tree=tree), photo(tree=tree)
        # Explicit timestamps: created a microsecond apart they could tie, and a tie in
        # `ordering` is not an order at all.
        TreePhoto.objects.filter(pk=older.pk).update(created_at=timezone.now() - timedelta(days=1))

        assert list(TreePhoto.objects.all()) == [newer, older]

    @pytest.mark.parametrize("field", ["tree", "uploaded_by"])
    def test_references_are_protected(self, field):
        """Repo invariant: FKs to trees and users use PROTECT, so history cannot vanish."""
        assert TreePhoto._meta.get_field(field).remote_field.on_delete is PROTECT

    def test_deleting_the_uploader_is_refused(self):
        entry = photo()

        with pytest.raises(ProtectedError):
            entry.uploaded_by.delete()


class TestStoredPath:
    def test_path_is_scoped_to_the_tree(self):
        tree = TreeFactory()

        assert str(tree.pk) in photo(tree=tree).image.name

    def test_path_does_not_reuse_the_uploaded_filename(self):
        """A name from the browser is user input: it may collide, or try to escape upwards."""
        entry = photo(name="../../../etc/passwd.jpg")

        assert "passwd" not in entry.image.name
        assert ".." not in entry.image.name

    def test_two_photos_of_one_tree_never_collide(self):
        tree = TreeFactory()

        first, second = photo(tree=tree), photo(tree=tree)

        assert first.image.name != second.image.name

    def test_stored_as_jpg(self):
        assert photo(name="rysunek.png").image.name.endswith(".jpg")


class TestRelation:
    def test_tree_reaches_its_photos(self):
        tree = TreeFactory()
        entry = photo(tree=tree)

        assert list(tree.photos.all()) == [entry]

    def test_dimensions_are_stored_for_the_img_tag(self):
        """Without width/height the card jumps while the photo loads."""
        entry = photo()
        entry.width, entry.height = 1600, 1200
        entry.save(update_fields=["width", "height"])

        assert (entry.width, entry.height) == (1600, 1200)
