"""factory_boy factories shared by the tests of all apps."""

from decimal import Decimal

import factory
from django.utils import timezone

from accounts.models import User
from trees.models import Locality, Tree

TEST_PASSWORD = "haslo-testowe-123"


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"wolontariusz{n}@przyklad.pl")
    display_name = factory.Sequence(lambda n: f"Wolontariusz {n}")
    password = factory.PostGenerationMethodCall("set_password", TEST_PASSWORD)

    @factory.post_generation
    def _save(obj, create, extracted, **kwargs):
        if create:
            obj.save()


class LocalityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Locality
        django_get_or_create = ["name"]

    name = factory.Sequence(lambda n: f"Miejscowość {n}")
    lat = Decimal("52.871000")
    lng = Decimal("19.651000")


class TreeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Tree

    locality = factory.SubFactory(LocalityFactory)
    lat = Decimal("52.872100")
    lng = Decimal("19.647800")
    species = "Lipa drobnolistna"
    planted_on = factory.LazyFunction(timezone.localdate)
    created_by = factory.SubFactory(UserFactory)
