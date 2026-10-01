"""The notices screen and the badge (UI doc §8.8).

A notice says that somebody was told to go and water a particular tree. That is their
business, so the first test here is that one person never sees another's — the same rule that
keeps volunteer names off the public card, applied to a different shape of data.

The badge is the only part of this feature that costs anything on every page in the
application, so its price has a test of its own.
"""

import pytest
from django.urls import reverse
from django.utils import timezone

from factories import TreeFactory, UserFactory
from notifications.models import Notification

pytestmark = pytest.mark.django_db

LIST_URL = reverse("notifications:list")


def notice(user, tree=None, read=False):
    return Notification.objects.create(
        user=user,
        tree=tree or TreeFactory(),
        read_at=timezone.now() if read else None,
    )


def open_url(entry):
    return reverse("notifications:open", kwargs={"notification_id": entry.pk})


class TestTheList:
    def test_shows_my_own(self, client):
        user = UserFactory()
        mine = notice(user, TreeFactory(species="Jabłoń – Ligol"))
        client.force_login(user)

        content = client.get(LIST_URL).content.decode()

        assert "Jabłoń – Ligol" in content
        assert reverse("trees:card", kwargs={"tree_id": mine.tree_id}) in content

    def test_never_somebody_elses(self, client):
        """The first rule of this screen."""
        notice(UserFactory(), TreeFactory(species="Cudza Grusza"))
        client.force_login(UserFactory())

        assert "Cudza Grusza" not in client.get(LIST_URL).content.decode()

    def test_newest_first(self, client):
        user = UserFactory()
        older = notice(user, TreeFactory(species="Starsza Lipa"))
        notice(user, TreeFactory(species="Nowszy Dąb"))
        Notification.objects.filter(pk=older.pk).update(
            created_at=timezone.now() - timezone.timedelta(days=2)
        )
        client.force_login(user)

        content = client.get(LIST_URL).content.decode()

        assert content.index("Nowszy Dąb") < content.index("Starsza Lipa")

    def test_shows_the_locality_and_the_status(self, client):
        """Same icon, label and colour as everywhere else (UI doc §6.6)."""
        from trees.models import Tree
        from trees.status_display import STATUS_DISPLAY

        user = UserFactory()
        notice(user, TreeFactory(status=Tree.Status.URGENT))
        client.force_login(user)

        content = client.get(LIST_URL).content.decode()

        assert STATUS_DISPLAY[Tree.Status.URGENT]["label"] in content

    def test_unread_are_marked_apart(self, client):
        user = UserFactory()
        notice(user, TreeFactory(species="Nieprzeczytana Lipa"))
        notice(user, TreeFactory(species="Przeczytany Dąb"), read=True)
        client.force_login(user)

        content = client.get(LIST_URL).content.decode()

        assert "unread" in content, "Nieprzeczytane muszą się czymś różnić"
        assert content.count("unread") == 1

    def test_empty_state_is_friendly(self, client):
        """UI doc §6: positive tone, also when there is nothing to show."""
        client.force_login(UserFactory())

        content = client.get(LIST_URL).content.decode()

        assert "Nic nowego" in content

    def test_anonymous_is_sent_to_login(self, client):
        assert client.get(LIST_URL).status_code == 302

    def test_no_query_per_notice(self, client, django_assert_num_queries):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        user = UserFactory()
        for _ in range(2):
            notice(user)
        client.force_login(user)
        with CaptureQueriesContext(connection) as captured:
            client.get(LIST_URL)
        baseline = len(captured.captured_queries)

        for _ in range(6):
            notice(user)
        with django_assert_num_queries(baseline):
            client.get(LIST_URL)


class TestOpening:
    def test_marks_read_and_goes_to_the_tree(self, client):
        user = UserFactory()
        entry = notice(user)
        client.force_login(user)

        response = client.post(open_url(entry))

        entry.refresh_from_db()
        assert entry.read_at is not None
        assert response["Location"] == reverse("trees:card", kwargs={"tree_id": entry.tree_id})

    def test_opening_twice_is_harmless(self, client):
        user = UserFactory()
        entry = notice(user)
        client.force_login(user)
        client.post(open_url(entry))
        first = Notification.objects.get(pk=entry.pk).read_at

        client.post(open_url(entry))

        assert Notification.objects.get(pk=entry.pk).read_at == first

    def test_cannot_open_somebody_elses(self, client):
        entry = notice(UserFactory())
        client.force_login(UserFactory())

        assert client.post(open_url(entry)).status_code == 404
        entry.refresh_from_db()
        assert entry.read_at is None

    def test_get_does_not_mark_read(self, client):
        """A prefetching browser must not clear somebody's notices for them."""
        user = UserFactory()
        entry = notice(user)
        client.force_login(user)

        assert client.get(open_url(entry)).status_code == 405
        entry.refresh_from_db()
        assert entry.read_at is None


class TestMarkAllRead:
    def test_clears_the_badge(self, client):
        user = UserFactory()
        for _ in range(3):
            notice(user)
        client.force_login(user)

        client.post(reverse("notifications:mark-all-read"))

        assert Notification.objects.filter(user=user, read_at__isnull=True).count() == 0

    def test_leaves_other_people_alone(self, client):
        stranger_notice = notice(UserFactory())
        user = UserFactory()
        notice(user)
        client.force_login(user)

        client.post(reverse("notifications:mark-all-read"))

        stranger_notice.refresh_from_db()
        assert stranger_notice.read_at is None


class TestTheBadge:
    def test_counts_unread_only(self, client):
        user = UserFactory()
        notice(user)
        notice(user)
        notice(user, read=True)
        client.force_login(user)

        content = client.get(reverse("trees:map")).content.decode()

        assert LIST_URL in content
        assert "notification-badge" in content
        assert ">2<" in content

    def test_hidden_when_nothing_is_unread(self, client):
        user = UserFactory()
        notice(user, read=True)
        client.force_login(user)

        content = client.get(reverse("trees:map")).content.decode()

        assert LIST_URL in content, "Link zostaje, znika tylko liczba"
        assert "notification-badge" not in content

    def test_anonymous_sees_no_link(self, client):
        assert LIST_URL not in client.get(reverse("trees:map")).content.decode()

    def test_costs_one_query(self, client, django_assert_num_queries):
        """It runs on every page in the application, so the price is pinned here."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        user = UserFactory()
        client.force_login(user)
        with CaptureQueriesContext(connection) as captured:
            client.get(reverse("trees:map"))
        baseline = len(captured.captured_queries)

        for _ in range(5):
            notice(user)

        with django_assert_num_queries(baseline):
            client.get(reverse("trees:map"))

    def test_costs_nothing_extra_for_anonymous(self, client, django_assert_num_queries):
        """A guest has no notices, so the badge must not make them pay for the lookup.

        Counted against the page's own cost rather than zero: the map asks about localities
        whether anybody is signed in or not.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as captured:
            client.get(reverse("trees:map"))
        baseline = len(captured.captured_queries)

        for _ in range(3):
            notice(UserFactory())

        with django_assert_num_queries(baseline):
            client.get(reverse("trees:map"))
