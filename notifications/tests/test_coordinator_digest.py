"""The morning digest for a coordinator (architecture doc §5.7, PoC „Dzisiejszy raport suszy").

Same job as the admin digest, bounded by the area. Two rules carry over unchanged and are
worth stating because they are easy to break when a third kind of recipient appears: at most
one e-mail per user per day, and a quiet area earns no e-mail at all — including on a day when
the rest of the organisation is on fire.
"""

import pytest
from django.core import mail

from accounts.models import User
from factories import LocalityFactory, TreeFactory, UserFactory, oversee
from notifications.selectors import coordinator_overview
from notifications.services import send_digests
from trees.models import Tree
from trees.tests.factories import assign

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _locmem(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.APP_BASE_URL = "https://drzewa.greeninnowacje.pl"


@pytest.fixture
def area():
    coordinator = UserFactory(role=User.Role.COORDINATOR, display_name="Koordynator")
    mine, theirs = LocalityFactory(name="Sierpc"), LocalityFactory(name="Płock")
    oversee(coordinator, mine)
    return coordinator, mine, theirs


def urgent_in(locality, **kwargs):
    return TreeFactory(locality=locality, status=Tree.Status.URGENT, **kwargs)


def sent_to(email):
    return [message for message in mail.outbox if email in message.to]


class TestOverviewSelector:
    def test_counts_only_the_area(self, area):
        coordinator, mine, theirs = area
        urgent_in(mine)
        urgent_in(theirs)

        overview = coordinator_overview(coordinator)

        assert overview["urgent_total"] == 1
        assert [row["name"] for row in overview["localities"]] == ["Sierpc"]

    def test_orphans_are_the_area_s_own(self, area):
        coordinator, mine, theirs = area
        orphan = urgent_in(mine)
        assign(urgent_in(mine), UserFactory())
        urgent_in(theirs)

        assert [tree.pk for tree in coordinator_overview(coordinator)["orphans"]] == [orphan.pk]

    def test_quiet_area_totals_zero(self, area):
        coordinator, mine, theirs = area
        TreeFactory(locality=mine, status=Tree.Status.OK)
        urgent_in(theirs)

        assert coordinator_overview(coordinator)["urgent_total"] == 0


class TestWhoGetsWhat:
    def test_coordinator_gets_the_area_digest(self, area):
        coordinator, mine, _ = area
        urgent_in(mine, species="Jabłoń – Ligol")

        send_digests()

        body = sent_to(coordinator.email)[0].body
        assert "Jabłoń – Ligol" in body
        assert "Sierpc" in body

    def test_a_quiet_area_earns_no_email(self, area):
        """Even when another locality is full of urgent trees."""
        coordinator, _, theirs = area
        urgent_in(theirs)

        send_digests()

        assert sent_to(coordinator.email) == []

    def test_another_area_never_leaks_in(self, area):
        coordinator, mine, theirs = area
        urgent_in(mine, species="Jabłoń – Ligol")
        urgent_in(theirs, species="Grusza – Konferencja")

        send_digests()

        assert "Grusza – Konferencja" not in sent_to(coordinator.email)[0].body

    def test_admin_digest_stays_global(self, area):
        _, mine, theirs = area
        admin = UserFactory(role=User.Role.ADMIN)
        urgent_in(mine, species="Jabłoń – Ligol")
        urgent_in(theirs, species="Grusza – Konferencja")

        send_digests()

        body = sent_to(admin.email)[0].body
        assert "Płock" in body and "Sierpc" in body

    def test_coordinator_who_is_also_a_caretaker_gets_one_email(self, area):
        """The rule that survived the admin case has to survive this one too."""
        coordinator, mine, _ = area
        tree = urgent_in(mine)
        assign(tree, coordinator)

        send_digests()

        messages = sent_to(coordinator.email)
        assert len(messages) == 1
        assert str(tree.pk) in messages[0].body, "Własne drzewa nie mogą wypaść z maila"

    def test_a_coordinator_with_a_quiet_area_still_hears_about_their_own_tree(self, area):
        """Their own urgent tree elsewhere is still their business as a volunteer."""
        coordinator, _, theirs = area
        tree = urgent_in(theirs)
        assign(tree, coordinator)

        send_digests()

        assert len(sent_to(coordinator.email)) == 1

    def test_daily_limit_applies(self, area):
        coordinator, mine, _ = area
        urgent_in(mine)

        send_digests()
        send_digests()

        assert len(sent_to(coordinator.email)) == 1

    def test_inactive_coordinator_is_skipped(self, area):
        coordinator, mine, _ = area
        coordinator.is_active = False
        coordinator.save(update_fields=["is_active"])
        urgent_in(mine)

        send_digests()

        assert sent_to(coordinator.email) == []


class TestContent:
    def test_names_the_area_rather_than_the_organisation(self, area):
        coordinator, mine, _ = area
        urgent_in(mine)

        send_digests()

        message = sent_to(coordinator.email)[0]
        assert "Sierpc" in message.subject or "Sierpc" in message.body

    def test_orphans_are_highlighted(self, area):
        coordinator, mine, _ = area
        urgent_in(mine)

        send_digests()

        assert "bez opiekuna" in sent_to(coordinator.email)[0].body.lower()

    def test_no_volunteer_names(self, area):
        """A digest may be forwarded on; it carries numbers and trees, not people."""
        coordinator, mine, _ = area
        caretaker = UserFactory(display_name="Jan Kowalski", email="jan@przyklad.pl")
        assign(urgent_in(mine), caretaker)

        send_digests()

        for message in sent_to(coordinator.email):
            body = message.body + "".join(part for part, _ in message.alternatives)
            assert caretaker.display_name not in body
            assert caretaker.email not in body
