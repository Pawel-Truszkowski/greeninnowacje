"""Uploading, showing and serving tree photos (Etap 2). Written before the implementation.

The visibility rule decided for this feature is simply "logged-in only": nothing serves
MEDIA_ROOT, so `trees:photo` is the one way a file leaves the server and `@login_required` on
it *is* the rule. A public QR card keeps the placeholder — a photo from a private garden shows
a house and the people in it, and the client has not yet answered whether that may be public.
"""

import io

import pytest
from django.urls import reverse
from PIL import Image

from factories import TreeFactory, UserFactory
from trees.models import TreePhoto
from trees.services import add_photo
from trees.tests.factories import assign

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


def image_file(name="zdjecie.jpg", size=(900, 600)):
    """A photo the test client can post, and that `add_photo` can also take directly.

    `.size` is what Django's own `UploadedFile` provides and what `process_upload` reads; the
    test client does not need it, a direct call does.
    """
    buffer = io.BytesIO()
    Image.new("RGB", size, "green").save(buffer, "JPEG")
    buffer.seek(0)
    buffer.name = name
    buffer.size = len(buffer.getvalue())
    return buffer


@pytest.fixture
def tree_and_caretaker():
    tree = TreeFactory()
    caretaker = UserFactory(display_name="Opiekun")
    assign(tree, caretaker)
    return tree, caretaker


@pytest.fixture
def stored_photo(tree_and_caretaker):
    tree, caretaker = tree_and_caretaker
    return add_photo(tree, caretaker, image_file()), tree, caretaker


class TestUploadFromTheCard:
    def url(self, tree):
        return reverse("trees:add-photo", kwargs={"tree_id": tree.pk})

    def test_caretaker_uploads_and_is_told_so(self, client, tree_and_caretaker):
        tree, caretaker = tree_and_caretaker
        client.force_login(caretaker)

        response = client.post(self.url(tree), {"image": image_file()}, follow=True)

        assert TreePhoto.objects.count() == 1
        assert any(message.level_tag == "success" for message in response.context["messages"])

    def test_unrelated_volunteer_gets_a_message_not_a_crash(self, client, tree_and_caretaker):
        tree, _ = tree_and_caretaker
        client.force_login(UserFactory())

        response = client.post(self.url(tree), {"image": image_file()}, follow=True)

        assert not TreePhoto.objects.exists()
        assert any(message.level_tag == "error" for message in response.context["messages"])

    def test_a_file_that_is_not_an_image_is_reported_to_the_user(self, client, tree_and_caretaker):
        """UI doc §107 asks for a „błąd zapisu zdjęcia" state, not a 500."""
        tree, caretaker = tree_and_caretaker
        client.force_login(caretaker)
        junk = io.BytesIO(b"to nie jest obraz")
        junk.name = "notatka.jpg"

        response = client.post(self.url(tree), {"image": junk}, follow=True)

        assert response.status_code == 200
        assert not TreePhoto.objects.exists()
        assert any(message.level_tag == "error" for message in response.context["messages"])

    def test_no_file_at_all_is_a_message_too(self, client, tree_and_caretaker):
        tree, caretaker = tree_and_caretaker
        client.force_login(caretaker)

        response = client.post(self.url(tree), {}, follow=True)

        assert response.status_code == 200
        assert not TreePhoto.objects.exists()

    def test_anonymous_is_sent_to_the_login_page(self, client, tree_and_caretaker):
        tree, _ = tree_and_caretaker

        assert client.post(self.url(tree), {"image": image_file()}).status_code == 302
        assert not TreePhoto.objects.exists()

    def test_rate_limited_upload_is_refused_with_a_message(
        self, client, settings, tree_and_caretaker
    ):
        settings.PHOTO_RATE_LIMIT = "1/h"
        tree, caretaker = tree_and_caretaker
        client.force_login(caretaker)
        client.post(self.url(tree), {"image": image_file()})

        response = client.post(self.url(tree), {"image": image_file()}, follow=True)

        assert TreePhoto.objects.count() == 1
        assert any(message.level_tag == "error" for message in response.context["messages"])


class TestRemoveFromTheCard:
    def url(self, photo):
        return reverse(
            "trees:remove-photo", kwargs={"tree_id": photo.tree_id, "photo_id": photo.pk}
        )

    def test_author_removes_their_photo(self, client, stored_photo):
        photo, _, caretaker = stored_photo
        client.force_login(caretaker)

        client.post(self.url(photo), follow=True)

        assert not TreePhoto.objects.exists()

    def test_someone_else_cannot(self, client, stored_photo):
        photo, _, _ = stored_photo
        client.force_login(UserFactory())

        response = client.post(self.url(photo), follow=True)

        assert TreePhoto.objects.count() == 1
        assert any(message.level_tag == "error" for message in response.context["messages"])

    def test_anonymous_cannot(self, client, stored_photo):
        photo, _, _ = stored_photo

        assert client.post(self.url(photo)).status_code == 302
        assert TreePhoto.objects.count() == 1


class TestServingTheFile:
    def url(self, photo):
        return reverse("trees:photo", kwargs={"photo_id": photo.pk})

    def test_logged_in_user_gets_the_jpeg(self, client, stored_photo):
        """Any logged-in user, not just the caretaker — that is the decided visibility rule."""
        photo, _, _ = stored_photo
        client.force_login(UserFactory())

        response = client.get(self.url(photo))

        assert response.status_code == 200
        assert response["Content-Type"] == "image/jpeg"

    def test_body_really_is_the_stored_image(self, client, stored_photo):
        photo, _, caretaker = stored_photo
        client.force_login(caretaker)

        response = client.get(self.url(photo))

        body = b"".join(response.streaming_content)
        assert Image.open(io.BytesIO(body)).format == "JPEG"

    def test_anonymous_is_sent_to_the_login_page(self, client, stored_photo):
        photo, _, _ = stored_photo

        assert client.get(self.url(photo)).status_code == 302

    def test_unknown_photo_is_a_404(self, client):
        import uuid

        client.force_login(UserFactory())

        url = reverse("trees:photo", kwargs={"photo_id": uuid.uuid4()})

        assert client.get(url).status_code == 404


class TestTheCardItself:
    def test_logged_in_card_shows_the_photo(self, client, stored_photo):
        photo, tree, caretaker = stored_photo
        client.force_login(caretaker)

        content = client.get(reverse("trees:card", kwargs={"tree_id": tree.pk})).content.decode()

        assert reverse("trees:photo", kwargs={"photo_id": photo.pk}) in content

    def test_public_card_shows_no_photo_at_all(self, client, stored_photo):
        """The QR card is public; a photo of a private garden is not.

        Checked by the serving path rather than by `<img`, because the page legitimately has
        two of those already: the logo in `base.html` and the tree's own QR code.
        """
        photo, tree, _ = stored_photo

        content = client.get(reverse("trees:card", kwargs={"tree_id": tree.pk})).content.decode()

        assert reverse("trees:photo", kwargs={"photo_id": photo.pk}) not in content
        assert "/zdjecie/" not in content

    def test_caretaker_sees_the_upload_form(self, client, tree_and_caretaker):
        tree, caretaker = tree_and_caretaker
        client.force_login(caretaker)

        content = client.get(reverse("trees:card", kwargs={"tree_id": tree.pk})).content.decode()

        assert reverse("trees:add-photo", kwargs={"tree_id": tree.pk}) in content

    def test_unrelated_volunteer_does_not_see_the_upload_form(self, client, tree_and_caretaker):
        tree, _ = tree_and_caretaker
        client.force_login(UserFactory())

        content = client.get(reverse("trees:card", kwargs={"tree_id": tree.pk})).content.decode()

        assert reverse("trees:add-photo", kwargs={"tree_id": tree.pk}) not in content

    def test_dimensions_are_in_the_markup(self, client, stored_photo):
        """`width`/`height` keep the card from jumping while the photo loads."""
        photo, tree, caretaker = stored_photo
        client.force_login(caretaker)

        content = client.get(reverse("trees:card", kwargs={"tree_id": tree.pk})).content.decode()

        assert f'width="{photo.width}"' in content
        assert f'height="{photo.height}"' in content


class TestJsonApi:
    def upload_url(self, tree):
        return reverse("trees-api:photos", kwargs={"tree_id": tree.pk})

    def detail_url(self, photo):
        return reverse(
            "trees-api:photo-detail", kwargs={"tree_id": photo.tree_id, "photo_id": photo.pk}
        )

    def test_caretaker_uploads(self, client, tree_and_caretaker):
        tree, caretaker = tree_and_caretaker
        client.force_login(caretaker)

        response = client.post(self.upload_url(tree), {"image": image_file()})

        assert response.status_code == 201
        assert response.json()["id"] == str(TreePhoto.objects.get().pk)
        assert (
            reverse("trees:photo", kwargs={"photo_id": TreePhoto.objects.get().pk})
            in (response.json()["url"])
        )

    def test_unrelated_volunteer_is_forbidden(self, client, tree_and_caretaker):
        tree, _ = tree_and_caretaker
        client.force_login(UserFactory())

        assert client.post(self.upload_url(tree), {"image": image_file()}).status_code == 403

    def test_broken_file_is_a_400_with_a_message(self, client, tree_and_caretaker):
        tree, caretaker = tree_and_caretaker
        client.force_login(caretaker)
        junk = io.BytesIO(b"nie obraz")
        junk.name = "x.jpg"

        response = client.post(self.upload_url(tree), {"image": junk})

        assert response.status_code == 400
        assert not TreePhoto.objects.exists()

    def test_author_deletes(self, client, stored_photo):
        photo, _, caretaker = stored_photo
        client.force_login(caretaker)

        assert client.delete(self.detail_url(photo)).status_code == 204
        assert not TreePhoto.objects.exists()

    def test_admin_deletes_anything(self, client, stored_photo):
        photo, _, _ = stored_photo
        client.force_login(UserFactory(role="admin"))

        assert client.delete(self.detail_url(photo)).status_code == 204

    def test_another_volunteer_cannot_delete(self, client, stored_photo):
        photo, _, _ = stored_photo
        client.force_login(UserFactory())

        assert client.delete(self.detail_url(photo)).status_code == 403
        assert TreePhoto.objects.count() == 1

    def test_anonymous_cannot_upload(self, client, tree_and_caretaker):
        tree, _ = tree_and_caretaker

        assert client.post(self.upload_url(tree), {"image": image_file()}).status_code == 403
