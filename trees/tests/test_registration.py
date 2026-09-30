"""Tree registration: duplicates, locality resolution, API and page (spec §4, §5.2)."""

import io
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
import respx
from django.urls import reverse
from django.utils import timezone
from PIL import Image

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
        monkeypatch.setattr("trees.nominatim._wait_for_slot", lambda wait=True: True)
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


class TestPhotoDuringRegistration:
    """A photo taken on the spot (PoC: the placeholder in the registration form)."""

    @pytest.fixture(autouse=True)
    def media_root(self, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)

    def photo(self, name="zdjecie.jpg"):
        buffer = io.BytesIO()
        Image.new("RGB", (800, 600), "green").save(buffer, "JPEG")
        buffer.seek(0)
        buffer.name = name
        return buffer

    def test_tree_and_photo_are_saved_together(self, client, volunteer):
        response = client.post(PAGE_URL, payload(photo=self.photo()), follow=True)

        tree = Tree.objects.get()
        assert response.status_code == 200
        assert tree.photos.count() == 1
        assert tree.photos.get().uploaded_by == volunteer

    def test_photo_is_optional(self, client, volunteer):
        client.post(PAGE_URL, payload(), follow=True)

        assert Tree.objects.get().photos.count() == 0

    def test_a_broken_photo_does_not_cost_the_tree(self, client, volunteer):
        """She is standing in a field: warn about the file, keep the tree."""
        junk = io.BytesIO(b"to nie jest obraz")
        junk.name = "notatka.jpg"

        response = client.post(PAGE_URL, payload(photo=junk), follow=True)

        tree = Tree.objects.get()
        assert tree.photos.count() == 0
        levels = [message.level_tag for message in response.context["messages"]]
        assert "warning" in levels
        assert "success" in levels, "Rejestracja mimo wszystko się udała"

    def test_duplicate_says_the_photo_has_to_be_picked_again(self, client, volunteer):
        TreeFactory(lat=SIERPC[0], lng=SIERPC[1])

        response = client.post(PAGE_URL, payload(photo=self.photo()))

        assert "Wybierz zdjęcie ponownie" in response.content.decode()
        assert Tree.objects.count() == 1, "Duplikat nie zapisuje drzewa"

    def test_duplicate_without_a_photo_says_nothing_about_photos(self, client, volunteer):
        TreeFactory(lat=SIERPC[0], lng=SIERPC[1])

        response = client.post(PAGE_URL, payload())

        assert "Wybierz zdjęcie ponownie" not in response.content.decode()

    def test_form_accepts_files_at_all(self, client, volunteer):
        """Without enctype="multipart/form-data" the file never arrives."""
        content = client.get(PAGE_URL).content.decode()

        assert 'enctype="multipart/form-data"' in content


class TestRegistrationScreenTexts:
    """The wording and layout agreed from the PoC (UI doc §8.5)."""

    def test_intro_sentence(self, client, volunteer):
        content = client.get(PAGE_URL).content.decode()

        assert "Stoisz przy drzewie? Świetnie" in content
        assert "przesuwając pinezkę" in content

    def test_location_card_has_a_heading_and_an_accuracy_slot(self, client, volunteer):
        content = client.get(PAGE_URL).content.decode()

        assert "Lokalizacja GPS" in content
        assert 'id="gps-accuracy"' in content, "Plakietka dokładności jest wypełniana skryptem"
        assert 'id="coords"' in content

    def test_locality_is_hidden_behind_a_toggle(self, client, volunteer):
        """The locality comes from the coordinates; typing it is the exception (PoC „zmień")."""
        content = client.get(PAGE_URL).content.decode()

        assert "<details" in content
        assert "zmień miejscowość" in content
        assert "miejscowość ustalimy automatycznie" in content

    def test_toggle_starts_closed(self, client, volunteer):
        assert '<details class="locality-override">' in client.get(PAGE_URL).content.decode()

    def test_toggle_opens_itself_when_the_geocoder_fails(self, client, volunteer, monkeypatch):
        """Then the field is the only way forward, so it must not be hidden behind a toggle."""
        monkeypatch.setattr("trees.services.reverse_locality", lambda lat, lng: None)

        content = client.post(PAGE_URL, payload()).content.decode()

        assert 'class="locality-override" open' in content
        assert "wpisz ją proszę ręcznie" in content

    def test_page_is_as_wide_as_the_rest_of_the_app(self, client, volunteer):
        """The PoC has no narrow variant here — the map and the location card need the room."""
        content = client.get(PAGE_URL).content.decode()

        assert '<main class="page">' in content

    def test_locality_hint_has_a_fallback_in_the_html(self, client, volunteer):
        """Without JavaScript the line still reads sensibly — the hint only replaces it."""
        content = client.get(PAGE_URL).content.decode()

        assert 'id="locality-hint"' in content
        assert "miejscowość ustalimy automatycznie" in content

    def test_page_points_the_script_at_the_hint_endpoint(self, client, volunteer):
        content = client.get(PAGE_URL).content.decode()

        assert reverse("trees-api:locality-hint") in content

    def test_photo_field_is_offered(self, client, volunteer):
        content = client.get(PAGE_URL).content.decode()

        assert 'name="photo"' in content
        assert 'accept="image/*"' in content, "Wybór plików ograniczony do obrazów"
        assert "capture=" not in content, (
            "`capture` wymusza aparat i odcina galerię — UI doc §106 chce obu dróg"
        )
