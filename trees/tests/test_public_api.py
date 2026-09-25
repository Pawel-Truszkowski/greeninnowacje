from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from factories import LocalityFactory, TreeFactory, UserFactory
from trees.models import Tree
from trees.tests.factories import assign, water
from weather.models import WeatherDaily

pytestmark = pytest.mark.django_db

LIST_URL = reverse("trees-api:list")


def card_url(tree):
    return reverse("trees-api:public", kwargs={"tree_id": tree.pk})


class TestTreeList:
    def test_returns_active_trees_only(self, client):
        active = TreeFactory()
        TreeFactory(lifecycle=Tree.Lifecycle.ARCHIVED)

        body = client.get(LIST_URL).json()

        assert [tree["id"] for tree in body] == [str(active.pk)]

    def test_payload_fields(self, client, user):
        tree = TreeFactory(species="Lipa drobnolistna", status=Tree.Status.SOON)
        water(tree, user, days_ago=2)
        assign(tree, user)

        (payload,) = client.get(LIST_URL).json()

        assert payload == {
            "id": str(tree.pk),
            "lat": float(tree.lat),
            "lng": float(tree.lng),
            "species": "Lipa drobnolistna",
            "status": "SOON",
            "locality_id": tree.locality_id,
            "last_watered_on": (timezone.localdate() - timedelta(days=2)).isoformat(),
            "has_caretaker": True,
            "is_mine": False,  # anonymous request
        }

    def test_tree_without_history(self, client):
        TreeFactory()
        (payload,) = client.get(LIST_URL).json()
        assert payload["last_watered_on"] is None and payload["has_caretaker"] is False

    def test_filter_by_status(self, client):
        urgent = TreeFactory(status=Tree.Status.URGENT)
        TreeFactory(status=Tree.Status.OK)

        body = client.get(LIST_URL, {"status": "URGENT"}).json()

        assert [tree["id"] for tree in body] == [str(urgent.pk)]

    def test_filter_by_locality(self, client):
        sierpc = LocalityFactory(name="Sierpc")
        mine = TreeFactory(locality=sierpc)
        TreeFactory(locality=LocalityFactory(name="Studzieniec"))

        body = client.get(LIST_URL, {"locality": sierpc.pk}).json()

        assert [tree["id"] for tree in body] == [str(mine.pk)]

    @pytest.mark.parametrize(
        ("params", "field"),
        [({"status": "MOKRE"}, "status"), ({"locality": "abc"}, "locality")],
    )
    def test_invalid_filters_rejected(self, client, params, field):
        response = client.get(LIST_URL, params)
        assert response.status_code == 400
        assert field in response.json()


class TestBboxFilter:
    """?bbox=west,south,east,north — Leaflet's bounds.toBBoxString() (spec §4)."""

    @pytest.fixture
    def trees(self):
        return {
            "inside": TreeFactory(lat=Decimal("52.8700"), lng=Decimal("19.6500")),
            "north": TreeFactory(lat=Decimal("52.9500"), lng=Decimal("19.6500")),
            "east": TreeFactory(lat=Decimal("52.8700"), lng=Decimal("19.9000")),
        }

    def test_returns_only_trees_inside(self, client, trees):
        body = client.get(LIST_URL, {"bbox": "19.60,52.85,19.70,52.89"}).json()

        assert [tree["id"] for tree in body] == [str(trees["inside"].pk)]

    def test_edges_are_inclusive(self, client, trees):
        body = client.get(LIST_URL, {"bbox": "19.65,52.87,19.90,52.95"}).json()

        assert {tree["id"] for tree in body} == {str(tree.pk) for tree in trees.values()}

    @pytest.mark.parametrize(
        ("bbox", "reason"),
        [
            ("19.6,52.8,19.7", "za mało wartości"),
            ("19.6,52.8,19.7,52.9,1", "za dużo wartości"),
            ("abc,52.8,19.7,52.9", "nie liczba"),
            ("nan,52.8,19.7,52.9", "nan"),
            ("inf,52.8,19.7,52.9", "inf"),
            ("19.6,52.9,19.7,52.8", "south > north"),
            ("19.7,52.8,19.6,52.9", "west > east"),
            ("19.6,-95,19.7,52.9", "szerokość poza zakresem"),
            ("-200,52.8,19.7,52.9", "długość poza zakresem"),
        ],
    )
    def test_malformed_bbox_is_400(self, client, bbox, reason):
        response = client.get(LIST_URL, {"bbox": bbox})

        assert response.status_code == 400, reason
        assert "bbox" in response.json()

    def test_empty_bbox_means_no_filter(self, client, trees):
        """An empty query param is the same as not sending it (as for status/locality)."""
        body = client.get(LIST_URL, {"bbox": ""}).json()

        assert len(body) == len(trees)

    def test_degenerate_bbox_is_allowed(self, client, trees):
        """A fully zoomed-in view can collapse to a point; that is not an error."""
        body = client.get(LIST_URL, {"bbox": "19.65,52.87,19.65,52.87"}).json()

        assert [tree["id"] for tree in body] == [str(trees["inside"].pk)]


class TestPublicCard:
    def test_unknown_tree_is_404(self, client):
        response = client.get(
            reverse("trees-api:public", kwargs={"tree_id": "00000000-0000-0000-0000-000000000000"})
        )
        assert response.status_code == 404

    def test_archived_tree_still_readable(self, client):
        tree = TreeFactory(lifecycle=Tree.Lifecycle.ARCHIVED)
        body = client.get(card_url(tree)).json()
        assert body["lifecycle"] == "archived"

    def test_history_has_dates_without_times(self, client, user):
        tree = TreeFactory()
        water(tree, user, days_ago=1)
        water(tree, user, days_ago=5)

        body = client.get(card_url(tree)).json()

        assert body["waterings"] == [
            (timezone.localdate() - timedelta(days=1)).isoformat(),
            (timezone.localdate() - timedelta(days=5)).isoformat(),
        ]
        assert body["waterings_total"] == 2

    def test_weather_window_keeps_missing_days_as_null(self, client):
        """The series covers finished days only — today's rainfall is still a forecast."""
        tree = TreeFactory()
        yesterday = timezone.localdate() - timedelta(days=1)
        WeatherDaily.objects.create(
            locality=tree.locality, day=yesterday, precip_mm=Decimal("3.20")
        )
        WeatherDaily.objects.create(
            locality=tree.locality, day=yesterday - timedelta(days=1), precip_mm=Decimal("0")
        )

        body = client.get(card_url(tree)).json()

        assert len(body["weather"]) == 14
        assert body["weather"][-1] == {"day": yesterday.isoformat(), "precip_mm": 3.2}
        assert body["weather"][-2]["precip_mm"] == 0.0
        assert body["weather"][0]["precip_mm"] is None
        assert body["rain_window_mm"] == 3.2
        assert body["weather_missing_days"] == 3  # 5-day window, 2 days known

    def test_caretaker_is_only_a_flag(self, client, user):
        tree = TreeFactory()
        assign(tree, user)
        body = client.get(card_url(tree)).json()
        assert body["has_caretaker"] is True


class TestNoPersonalData:
    """Spec §7: public responses must not leak volunteer identities."""

    @pytest.fixture
    def tree_with_people(self):
        author = UserFactory(display_name="Autor Testowy", email="autor@tajne.example")
        waterer = UserFactory(display_name="Podlewacz Testowy", email="podlewacz@tajne.example")
        caretaker = UserFactory(display_name="Opiekun Testowy", email="opiekun@tajne.example")
        tree = TreeFactory(created_by=author)
        water(tree, waterer)
        assign(tree, caretaker)
        return tree

    @pytest.fixture
    def secrets(self):
        return ["Autor Testowy", "Podlewacz Testowy", "Opiekun Testowy", "tajne.example"]

    def test_card_api(self, client, tree_with_people, secrets):
        content = client.get(card_url(tree_with_people)).content.decode()
        assert not [secret for secret in secrets if secret in content]

    def test_list_api(self, client, tree_with_people, secrets):
        content = client.get(LIST_URL).content.decode()
        assert not [secret for secret in secrets if secret in content]

    def test_card_page(self, client, tree_with_people, secrets):
        url = reverse("trees:card", kwargs={"tree_id": tree_with_people.pk})
        content = client.get(url).content.decode()
        assert not [secret for secret in secrets if secret in content]


class TestCardPage:
    def test_renders_species_and_history(self, client, user):
        tree = TreeFactory(species="Dąb szypułkowy")
        water(tree, user)

        response = client.get(reverse("trees:card", kwargs={"tree_id": tree.pk}))

        assert response.status_code == 200
        assert "Dąb szypułkowy" in response.content.decode()

    def test_user_text_is_escaped(self, client):
        tree = TreeFactory(species="<script>alert('xss')</script>", notes="<img src=x onerror=1>")

        content = client.get(reverse("trees:card", kwargs={"tree_id": tree.pk})).content.decode()

        assert "<script>alert" not in content
        assert "&lt;script&gt;alert" in content
        assert "<img src=x" not in content
