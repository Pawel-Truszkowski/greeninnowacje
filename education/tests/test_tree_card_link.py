"""A tree card (the page behind the QR code) links to the guide of the tree's species."""

import pytest
from django.urls import reverse

from education.models import SpeciesGuide
from factories import TreeFactory

pytestmark = pytest.mark.django_db

GUIDE_URL = reverse("education:species", args=["lipa-drobnolistna"])


def card_html(client, tree):
    return client.get(reverse("trees:card", kwargs={"tree_id": tree.pk})).content.decode()


@pytest.mark.parametrize("species", ["Lipa drobnolistna", "  lipa DROBNOLISTNA "])
def test_links_to_the_guide_of_its_species(client, species):
    html = card_html(client, TreeFactory(species=species))

    assert f'href="{GUIDE_URL}"' in html
    assert "Poznaj ten gatunek" in html


def test_species_without_guide_has_no_link(client):
    # In the catalogue, but no infographic yet.
    html = card_html(client, TreeFactory(species="Jarząb pospolity"))

    assert "Poznaj ten gatunek" not in html


def test_unpublished_guide_is_not_linked(client):
    SpeciesGuide.objects.filter(slug="lipa-drobnolistna").update(is_published=False)

    html = card_html(client, TreeFactory(species="Lipa drobnolistna"))

    assert "Poznaj ten gatunek" not in html


def test_logged_in_card_links_too(client, user):
    client.force_login(user)

    html = card_html(client, TreeFactory(species="Lipa drobnolistna"))

    assert f'href="{GUIDE_URL}"' in html


def test_public_api_card_is_unchanged(client):
    # The link is presentation only; public_tree_card() defines what the API exposes.
    tree = TreeFactory(species="Lipa drobnolistna")

    body = client.get(reverse("trees-api:public", kwargs={"tree_id": tree.pk})).json()

    assert "guide" not in body and "slug" not in str(body)
