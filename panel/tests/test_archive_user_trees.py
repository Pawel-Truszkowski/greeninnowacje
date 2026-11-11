"""Archive everything one account registered — cleaning up after fake trees (anti-spam).

One click on the person's panel page takes their trees off the map and, by default, closes
the account. Trees are archived, never deleted (spec §3), so a mistake is undone per tree
from `/admin/drzewa`.
"""

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from accounts.models import User
from factories import TreeFactory, UserFactory
from trees.models import Tree
from trees.services import archive_trees_of

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin(client):
    person = UserFactory(role=User.Role.ADMIN)
    client.force_login(person)
    return person


@pytest.fixture
def spammer():
    return UserFactory(display_name="Fikcyjny Sadownik")


def url(person):
    return reverse("panel:archive-user-trees", kwargs={"user_id": person.pk})


def lifecycles(person):
    return set(Tree.objects.filter(created_by=person).values_list("lifecycle", flat=True))


class TestService:
    def test_archives_only_this_persons_active_trees(self, spammer):
        TreeFactory.create_batch(3, created_by=spammer)
        TreeFactory(created_by=spammer, lifecycle=Tree.Lifecycle.ARCHIVED)
        someone_elses = TreeFactory()

        archived = archive_trees_of(spammer)

        assert archived == 3, "Liczy tylko drzewa, które naprawdę zmieniły stan"
        assert lifecycles(spammer) == {Tree.Lifecycle.ARCHIVED}
        someone_elses.refresh_from_db()
        assert someone_elses.lifecycle == Tree.Lifecycle.ACTIVE

    def test_nothing_to_archive(self, spammer):
        assert archive_trees_of(spammer) == 0


class TestPanelAction:
    def test_archives_and_deactivates_by_default(self, client, admin, spammer):
        TreeFactory.create_batch(2, created_by=spammer)

        response = client.post(url(spammer), {"deactivate": "on"})

        assert response.status_code == 302
        assert response.url == reverse("panel:edit-user", kwargs={"user_id": spammer.pk})
        assert lifecycles(spammer) == {Tree.Lifecycle.ARCHIVED}
        spammer.refresh_from_db()
        assert not spammer.is_active
        assert [m.level_tag for m in get_messages(response.wsgi_request)] == ["success"]

    def test_unticked_checkbox_keeps_the_account(self, client, admin, spammer):
        TreeFactory(created_by=spammer)

        client.post(url(spammer), {})

        assert lifecycles(spammer) == {Tree.Lifecycle.ARCHIVED}
        spammer.refresh_from_db()
        assert spammer.is_active

    def test_admin_cannot_deactivate_themselves(self, client, admin):
        """Same rule as the user form: locking yourself out takes one click."""
        own_tree = TreeFactory(created_by=admin)

        response = client.post(url(admin), {"deactivate": "on"})

        admin.refresh_from_db()
        own_tree.refresh_from_db()
        assert admin.is_active
        assert own_tree.lifecycle == Tree.Lifecycle.ACTIVE, "Odmowa nie zostawia połowy zmian"
        assert [m.level_tag for m in get_messages(response.wsgi_request)] == ["error"]

    def test_admin_may_archive_own_trees_without_deactivating(self, client, admin):
        TreeFactory(created_by=admin)

        client.post(url(admin), {})

        assert lifecycles(admin) == {Tree.Lifecycle.ARCHIVED}

    def test_archived_trees_leave_the_public_map(self, client, admin, spammer):
        tree = TreeFactory(created_by=spammer)

        client.post(url(spammer), {"deactivate": "on"})
        client.logout()

        ids = {item["id"] for item in client.get(reverse("trees-api:list")).json()}
        assert str(tree.pk) not in ids

    def test_get_is_not_allowed(self, client, admin, spammer):
        assert client.get(url(spammer)).status_code == 405

    def test_unknown_user_is_404(self, client, admin):
        missing = reverse(
            "panel:archive-user-trees", kwargs={"user_id": "00000000-0000-0000-0000-000000000000"}
        )
        assert client.post(missing).status_code == 404


class TestUserPage:
    def test_offers_the_action_with_deactivation_ticked(self, client, admin, spammer):
        TreeFactory(created_by=spammer)

        content = client.get(reverse("panel:edit-user", kwargs={"user_id": spammer.pk}))
        content = content.content.decode()

        assert f'action="{url(spammer)}"' in content
        assert 'name="deactivate"' in content
        assert "checked" in content.split('name="deactivate"')[1].split(">")[0]

    def test_hidden_when_there_is_nothing_to_archive(self, client, admin, spammer):
        TreeFactory(created_by=spammer, lifecycle=Tree.Lifecycle.ARCHIVED)

        content = client.get(reverse("panel:edit-user", kwargs={"user_id": spammer.pk}))

        assert url(spammer) not in content.content.decode()
