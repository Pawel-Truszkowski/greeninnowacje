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
