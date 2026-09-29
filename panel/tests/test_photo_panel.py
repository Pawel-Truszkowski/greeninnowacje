"""Photo moderation in the admin panel (Etap 2). Written before the implementation.

The one test that has to stay honest is `test_removing_a_photo_deletes_the_file`: a moderator
told somebody „usunięte" and that has to be true on disk, not only in the table. A bulk
`queryset.delete()` would pass a row-only assertion while leaving the picture on the server.
"""

import io

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from PIL import Image

from factories import LocalityFactory, TreeFactory, UserFactory
from panel.selectors import recent_photos
from trees.models import TreePhoto
from trees.services import add_photo
from trees.tests.factories import assign

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


def upload(name="zdjecie.jpg"):
    buffer = io.BytesIO()
    Image.new("RGB", (600, 400), "green").save(buffer, "JPEG")
    buffer.seek(0)
    buffer.name = name
    buffer.size = len(buffer.getvalue())
    return buffer


@pytest.fixture
def photo():
    volunteer = UserFactory(display_name="Anna Kowalska")
    tree = TreeFactory(species="Jabłoń – Ligol", locality=LocalityFactory(name="Żółkiewka"))
    assign(tree, volunteer)
    return add_photo(tree, volunteer, upload())


@pytest.fixture
def as_admin(client):
    client.force_login(UserFactory(role="admin"))
    return client


class TestSelector:
    def test_newest_first(self, photo):
        newer = add_photo(photo.tree, photo.uploaded_by, upload())

        assert [entry.pk for entry in recent_photos()] == [newer.pk, photo.pk]

    def test_limit_is_respected(self, photo):
        add_photo(photo.tree, photo.uploaded_by, upload())

        assert len(recent_photos(limit=1)) == 1

    def test_no_query_per_photo(self, photo, django_assert_num_queries):
        """The list shows the tree, its locality and the uploader — all joined, not looked up."""
        for _ in range(2):
            add_photo(photo.tree, photo.uploaded_by, upload())
        with CaptureQueriesContext(connection) as captured:
            for entry in recent_photos():
                _ = (entry.tree.species, entry.tree.locality.name, entry.uploaded_by.display_name)
        baseline = len(captured.captured_queries)

        for _ in range(5):
            add_photo(photo.tree, photo.uploaded_by, upload())
        with django_assert_num_queries(baseline):
            for entry in recent_photos():
                _ = (entry.tree.species, entry.tree.locality.name, entry.uploaded_by.display_name)


class TestPage:
    def test_shows_the_tree_the_place_the_author_and_the_date(self, as_admin, photo):
        content = as_admin.get(reverse("panel:photos")).content.decode()

        assert "Jabłoń – Ligol" in content
        assert "Żółkiewka" in content
        assert "Anna Kowalska" in content
        assert reverse("trees:photo", kwargs={"photo_id": photo.pk}) in content

    def test_links_to_the_tree_card(self, as_admin, photo):
        content = as_admin.get(reverse("panel:photos")).content.decode()

        assert reverse("trees:card", kwargs={"tree_id": photo.tree_id}) in content

    def test_empty_state(self, as_admin):
        content = as_admin.get(reverse("panel:photos")).content.decode()

        assert "Brak zdjęć" in content

    def test_is_in_the_panel_navigation(self, as_admin):
        content = as_admin.get(reverse("panel:dashboard")).content.decode()

        assert reverse("panel:photos") in content


class TestRemoval:
    def url(self, photo):
        return reverse("panel:remove-photo", kwargs={"photo_id": photo.pk})

    def test_removing_a_photo_deletes_the_file(self, as_admin, photo, media_root):
        path = media_root / photo.image.name
        assert path.exists(), "Bez pliku na dysku test nic nie sprawdza"

        as_admin.post(self.url(photo))

        assert not TreePhoto.objects.exists()
        assert not path.exists(), "Wiersz zniknął, a plik został — to nie jest usunięcie"

    def test_admin_may_remove_someone_elses_photo(self, as_admin, photo):
        """That is the point of moderation: the uploader is not the one asking."""
        as_admin.post(self.url(photo))

        assert not TreePhoto.objects.exists()

    def test_volunteer_is_forbidden(self, client, photo):
        client.force_login(UserFactory())

        assert client.post(self.url(photo)).status_code == 403
        assert TreePhoto.objects.count() == 1

    def test_anonymous_goes_to_the_login_page(self, client, photo):
        assert client.post(self.url(photo)).status_code == 302
        assert TreePhoto.objects.count() == 1

    def test_get_is_not_enough(self, as_admin, photo):
        """Deleting is a POST; a link a crawler could follow must not remove anything."""
        assert as_admin.get(self.url(photo)).status_code == 405
        assert TreePhoto.objects.count() == 1
