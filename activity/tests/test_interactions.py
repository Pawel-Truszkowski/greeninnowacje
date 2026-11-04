"""Interactions with trees as activity events. Written before the code.

The events are written from `trees/services.py`, inside the same transaction as the change
they describe. That gives the two rules tested here:

* every successful operation leaves exactly one event, with the person and the tree;
* a refused one leaves none — the log must never claim something that did not happen.

Whose name goes on a caretaker event: the caretaker's. When a coordinator assigns or
releases somebody, the event says whose care started or ended, because that is what the
activity table per volunteer counts.
"""

import io
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from activity.models import ActivityEvent
from factories import LocalityFactory, TreeFactory, UserFactory, oversee
from trees.services import (
    MAX_PHOTOS_PER_TREE,
    CaretakerConflict,
    DuplicateTree,
    PhotoNotAllowed,
    add_photo,
    assign_caretaker,
    assign_caretaker_for,
    record_watering,
    register_tree,
    release_caretaker,
    release_caretaker_of,
)
from trees.tests.factories import assign

pytestmark = pytest.mark.django_db

Kind = ActivityEvent.Kind


def events(kind):
    return list(ActivityEvent.objects.filter(kind=kind))


def jpeg(name="zdjecie.jpg"):
    buffer = io.BytesIO()
    Image.new("RGB", (900, 600), "green").save(buffer, "JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


@pytest.fixture
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


class TestWatering:
    def test_service_records_one_event(self, tree, user):
        record_watering(tree, user)

        [event] = events(Kind.WATERING)
        assert (event.user, event.tree) == (user, tree)

    def test_the_page_goes_through_the_service(self, client, tree, user):
        client.force_login(user)

        client.post(reverse("trees:water", kwargs={"tree_id": tree.pk}))

        assert len(events(Kind.WATERING)) == 1


class TestCare:
    def test_taking_care_records_one_event(self, tree, user):
        assign_caretaker(tree, user)

        [event] = events(Kind.CARE_TAKEN)
        assert (event.user, event.tree) == (user, tree)

    def test_a_lost_race_records_nothing(self, tree, user):
        assign(tree, UserFactory())

        with pytest.raises(CaretakerConflict):
            assign_caretaker(tree, user)

        assert not events(Kind.CARE_TAKEN)

    def test_releasing_records_one_event(self, tree, user):
        assign(tree, user)

        release_caretaker(tree, user)

        [event] = events(Kind.CARE_RELEASED)
        assert (event.user, event.tree) == (user, tree)

    def test_releasing_nothing_records_nothing(self, tree, user):
        assert release_caretaker(tree, user) is False

        assert not events(Kind.CARE_RELEASED)

    def test_coordinator_assignment_is_the_volunteers_event(self, user):
        coordinator = UserFactory(role="coordinator")
        locality = LocalityFactory()
        oversee(coordinator, locality)
        tree = TreeFactory(locality=locality)

        assign_caretaker_for(tree, user, by=coordinator)

        [event] = events(Kind.CARE_TAKEN)
        assert event.user == user

    def test_coordinator_release_is_the_former_caretakers_event(self, user):
        coordinator = UserFactory(role="coordinator")
        locality = LocalityFactory()
        oversee(coordinator, locality)
        tree = TreeFactory(locality=locality)
        assign(tree, user)

        release_caretaker_of(tree, by=coordinator)

        [event] = events(Kind.CARE_RELEASED)
        assert (event.user, event.tree) == (user, tree)


class TestRegistration:
    POINT = {"lat": Decimal("52.880000"), "lng": Decimal("19.660000"), "species": "Lipa"}

    def test_registering_records_one_event(self, user):
        tree = register_tree(user, locality_name="Sierpc", **self.POINT)

        [event] = events(Kind.TREE_REGISTERED)
        assert (event.user, event.tree) == (user, tree)

    def test_a_refused_duplicate_records_nothing(self, user):
        TreeFactory(lat=self.POINT["lat"], lng=self.POINT["lng"])

        with pytest.raises(DuplicateTree):
            register_tree(user, locality_name="Sierpc", **self.POINT)

        assert not events(Kind.TREE_REGISTERED)


class TestPhotos:
    def test_adding_a_photo_records_one_event(self, media_root, user):
        tree = TreeFactory(created_by=user)

        add_photo(tree, user, jpeg())

        [event] = events(Kind.PHOTO_ADDED)
        assert (event.user, event.tree) == (user, tree)

    def test_a_refused_photo_records_nothing(self, media_root, tree, user):
        with pytest.raises(PhotoNotAllowed):
            add_photo(tree, user, jpeg())  # not the author, not the caretaker

        assert not events(Kind.PHOTO_ADDED)

    def test_the_photo_limit_records_nothing(self, media_root, user):
        tree = TreeFactory(created_by=user)
        for _ in range(MAX_PHOTOS_PER_TREE):
            add_photo(tree, user, jpeg())
        ActivityEvent.objects.filter(kind=Kind.PHOTO_ADDED).delete()

        with pytest.raises(PhotoNotAllowed):
            add_photo(tree, user, jpeg())

        assert not events(Kind.PHOTO_ADDED)


class TestCardViews:
    """A QR scan lands on the public card. Counted anonymously — no user, no IP."""

    @pytest.mark.parametrize("name", ["trees:card", "trees-api:public"])
    def test_anonymous_visit_records_a_card_view(self, client, tree, name):
        client.get(reverse(name, kwargs={"tree_id": tree.pk}))

        [event] = events(Kind.CARD_VIEW)
        assert event.user is None
        assert event.tree == tree

    @pytest.mark.parametrize("name", ["trees:card", "trees-api:public"])
    def test_signed_in_visit_is_not_a_card_view(self, client, tree, user, name):
        """Volunteers open cards all day; counting them would drown the QR scans."""
        client.force_login(user)

        client.get(reverse(name, kwargs={"tree_id": tree.pk}))

        assert not events(Kind.CARD_VIEW)

    def test_missing_tree_records_nothing(self, client):
        response = client.get(
            reverse("trees:card", kwargs={"tree_id": "00000000-0000-0000-0000-000000000000"})
        )

        assert response.status_code == 404
        assert not events(Kind.CARD_VIEW)
