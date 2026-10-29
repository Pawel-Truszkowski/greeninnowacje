import pytest

from factories import LocalityFactory, TreeFactory, UserFactory


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def admin_user(db):
    return UserFactory(role="admin")


@pytest.fixture
def locality(db):
    return LocalityFactory()


@pytest.fixture
def tree(db):
    return TreeFactory()


@pytest.fixture
def empty_species_catalogue(db):
    """Start from an empty species catalogue instead of the seeded one.

    Species guides go first: each one PROTECTs its catalogue entry.
    """
    from education.models import SpeciesGuide
    from trees.models import TreeSpecies

    SpeciesGuide.objects.all().delete()
    TreeSpecies.objects.all().delete()
