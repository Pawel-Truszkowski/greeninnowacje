"""Tree registration: duplicates, locality resolution, API and page (spec §4, §5.2)."""

from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
import respx
from django.urls import reverse
from django.utils import timezone

from factories import LocalityFactory, TreeFactory, UserFactory
from trees.models import Tree
from trees.services import DuplicateTree, find_duplicate, register_tree, resolve_locality

pytestmark = pytest.mark.django_db

SIERPC = (Decimal("52.871000"), Decimal("19.651000"))
CREATE_URL = reverse("trees-api:create")
PAGE_URL = reverse("trees:register")


@pytest.fixture(autouse=True)
def no_geocoder(monkeypatch):
    """Tests must not depend on Nominatim (spec §9); the name comes back as Sierpc."""
    monkeypatch.setattr("trees.services.reverse_locality", lambda lat, lng: "Sierpc")


@pytest.fixture
def volunteer(client):
    user = UserFactory()
    client.force_login(user)
    return user


def payload(**overrides):
    return {
        "species": "Lipa drobnolistna",
        "planted_on": timezone.localdate().isoformat(),
        "planted_by": "Wolontariusze",
        "notes": "",
        "lat": "52.871000",
        "lng": "19.651000",
        "gps_accuracy_m": "4.2",
    } | overrides


def offset_by_metres(metres):
    """Latitude offset roughly equal to `metres` (1° of latitude ≈ 111.2 km)."""
    return Decimal(str(round(metres / 111_195, 8)))


class TestFindDuplicate:
    def test_no_trees_nearby(self):
        TreeFactory(lat=SIERPC[0] + offset_by_metres(50), lng=SIERPC[1])
        assert find_duplicate(*SIERPC) is None

    def test_tree_within_two_metres(self):
        existing = TreeFactory(lat=SIERPC[0] + offset_by_metres(1.5), lng=SIERPC[1])

        found = find_duplicate(*SIERPC)

        assert found is not None
        tree, distance = found
        assert tree == existing and distance == pytest.approx(1.5, abs=0.2)

    def test_tree_just_outside_the_radius(self):
        TreeFactory(lat=SIERPC[0] + offset_by_metres(2.6), lng=SIERPC[1])
        assert find_duplicate(*SIERPC) is None

    def test_returns_the_nearest_of_several(self):
        TreeFactory(lat=SIERPC[0] + offset_by_metres(1.8), lng=SIERPC[1])
        nearest = TreeFactory(lat=SIERPC[0] + offset_by_metres(0.4), lng=SIERPC[1])

        tree, distance = find_duplicate(*SIERPC)

        assert tree == nearest and distance < 1

    def test_archived_trees_do_not_block_the_spot(self):
        TreeFactory(lat=SIERPC[0], lng=SIERPC[1], lifecycle=Tree.Lifecycle.ARCHIVED)
        assert find_duplicate(*SIERPC) is None

    def test_longitude_offsets_are_measured_in_metres_too(self):
        """A degree of longitude is ~68 km here, so 0.00002° east is ~1.4 m, not 2.2 m."""
        existing = TreeFactory(lat=SIERPC[0], lng=SIERPC[1] + Decimal("0.00002"))

        found = find_duplicate(*SIERPC)

        assert found is not None and found[0] == existing


class TestResolveLocality:
    def test_reuses_existing_locality_ignoring_case(self):
        existing = LocalityFactory(name="Sierpc")

        assert resolve_locality(*SIERPC, name="sierpc") == existing

    def test_creates_locality_with_the_tree_as_centroid(self):
        locality = resolve_locality(*SIERPC, name="Studzieniec")

        assert locality.name == "Studzieniec"
        assert (locality.lat, locality.lng) == SIERPC

    def test_typed_name_wins_over_the_geocoder(self):
        assert resolve_locality(*SIERPC, name="Rachocin").name == "Rachocin"

    def test_falls_back_to_the_geocoder(self):
        assert resolve_locality(*SIERPC).name == "Sierpc"


class TestRegisterTreeApi:
    def test_creates_tree(self, client, volunteer):
        response = client.post(CREATE_URL, payload(), content_type="application/json")

        assert response.status_code == 201
        tree = Tree.objects.get(pk=response.json()["id"])
        assert tree.created_by == volunteer
        assert tree.locality.name == "Sierpc"
        assert response.json()["url"].endswith(str(tree.pk))

    def test_freshly_planted_tree_is_ok(self, client, volunteer):
        """Planting includes watering, so a new tree starts green, not alarming."""
        response = client.post(CREATE_URL, payload(), content_type="application/json")
        assert response.json()["status"] == Tree.Status.OK

    def test_duplicate_returns_409_with_details(self, client, volunteer):
        existing = TreeFactory(
            lat=SIERPC[0] + offset_by_metres(1.2), lng=SIERPC[1], species="Dąb szypułkowy"
        )

        response = client.post(CREATE_URL, payload(), content_type="application/json")

        assert response.status_code == 409
        duplicate = response.json()["duplicate"]
        assert duplicate["id"] == str(existing.pk)
        assert duplicate["species"] == "Dąb szypułkowy"
        assert duplicate["distance_m"] == pytest.approx(1.2, abs=0.3)
        assert Tree.objects.count() == 1

    def test_force_saves_anyway(self, client, volunteer):
        TreeFactory(lat=SIERPC[0], lng=SIERPC[1])

        response = client.post(CREATE_URL, payload(force=True), content_type="application/json")

        assert response.status_code == 201
        assert Tree.objects.count() == 2

    def test_invalid_payload_is_400(self, client, volunteer):
        response = client.post(
            CREATE_URL, payload(species="", lat=""), content_type="application/json"
        )

        assert response.status_code == 400
        assert "species" in response.json()["errors"]

    def test_anonymous_cannot_register(self, client):
        response = client.post(CREATE_URL, payload(), content_type="application/json")

        assert response.status_code == 403
        assert not Tree.objects.exists()

    def test_unknown_locality_asks_for_a_name(self, client, volunteer, monkeypatch):
        monkeypatch.setattr("trees.services.reverse_locality", lambda lat, lng: None)

        response = client.post(CREATE_URL, payload(), content_type="application/json")

        assert response.status_code == 400
        assert "locality_name" in response.json()["errors"]


class TestRegisterTreePage:
    def test_saves_and_redirects_to_the_card(self, client, volunteer):
        response = client.post(PAGE_URL, payload(), follow=True)

        tree = Tree.objects.get()
        assert response.redirect_chain[-1][0] == reverse("trees:card", kwargs={"tree_id": tree.pk})
        assert "Drzewo zarejestrowane" in response.content.decode()

    def test_duplicate_shows_the_question(self, client, volunteer):
        TreeFactory(lat=SIERPC[0], lng=SIERPC[1], species="Klon zwyczajny")

        content = client.post(PAGE_URL, payload()).content.decode()

        assert "Czy to nie to samo drzewo?" in content
        assert "Klon zwyczajny" in content
        assert Tree.objects.count() == 1

    def test_confirming_saves_the_second_tree(self, client, volunteer):
        TreeFactory(lat=SIERPC[0], lng=SIERPC[1])

        client.post(PAGE_URL, payload(force="1"))

        assert Tree.objects.count() == 2

    def test_anonymous_is_sent_to_login(self, client):
        response = client.get(PAGE_URL)
        assert response.status_code == 302 and reverse("accounts:login") in response.url


class TestRegistrationUsesGeocoder:
    """The one test that exercises the real client, with the HTTP call mocked."""

    @respx.mock
    def test_locality_comes_from_nominatim(self, client, volunteer, monkeypatch):
        monkeypatch.undo()  # drop the autouse stub, use the real reverse_locality
        monkeypatch.setattr("trees.nominatim._wait_for_slot", lambda: None)
        respx.get(url__startswith="https://nominatim.openstreetmap.org/reverse").mock(
            return_value=httpx.Response(200, json={"address": {"village": "Studzieniec"}})
        )

        client.post(CREATE_URL, payload(), content_type="application/json")

        assert Tree.objects.get().locality.name == "Studzieniec"


def test_register_tree_service_raises_duplicate():
    """Service-level guard: the exception carries what the UI needs to ask the question."""
    user = UserFactory()
    existing = TreeFactory(lat=SIERPC[0], lng=SIERPC[1])

    with pytest.raises(DuplicateTree) as error:
        register_tree(
            user,
            lat=SIERPC[0],
            lng=SIERPC[1],
            species="Lipa",
            planted_on=timezone.localdate() - timedelta(days=1),
            planted_by="",
            notes="",
            gps_accuracy_m=None,
        )

    assert error.value.existing == existing
