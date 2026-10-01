"""„📣 Poproś wolontariuszy o pomoc" — the appeal a coordinator sends by hand (PoC).

The tension worth testing is between two things the specification says plainly. A coordinator
must be able to call for help, and a volunteer gets at most one e-mail a day (spec §5.3). The
limit wins — it is unconditional — so the appeal reports how far it actually reached. A
coordinator who does not know their appeal went to three people out of eight is worse off
than one who does.
"""

import pytest
from django.core import mail
from django.urls import reverse

from accounts.models import User
from factories import LocalityFactory, TreeFactory, UserFactory, oversee
from notifications.models import EmailLog
from notifications.services import send_area_appeal
from trees.models import Tree
from trees.tests.factories import assign

pytestmark = pytest.mark.django_db

APPEAL_URL = reverse("coordinator:appeal")


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


def caretaker_in(locality, name, status=Tree.Status.URGENT):
    volunteer = UserFactory(display_name=name)
    assign(TreeFactory(locality=locality, status=status), volunteer)
    return volunteer


class TestWhoHearsIt:
    def test_volunteers_in_the_area(self, area):
        coordinator, mine, _ = area
        anna = caretaker_in(mine, "Anna")

        result = send_area_appeal(coordinator)

        assert result.sent == 1
        assert [m.to for m in mail.outbox] == [[anna.email]]

    def test_volunteers_elsewhere_do_not(self, area):
        """Mailing strangers about a locality they have never visited is not an appeal."""
        coordinator, _, theirs = area
        caretaker_in(theirs, "Obcy")

        assert send_area_appeal(coordinator).sent == 0
        assert mail.outbox == []

    def test_a_volunteer_with_no_trees_is_not_written_to(self, area):
        coordinator, mine, _ = area
        UserFactory(display_name="Bez drzew")
        caretaker_in(mine, "Anna")

        assert send_area_appeal(coordinator).sent == 1

    def test_inactive_accounts_are_skipped(self, area):
        coordinator, mine, _ = area
        volunteer = caretaker_in(mine, "Zablokowana")
        volunteer.is_active = False
        volunteer.save(update_fields=["is_active"])

        assert send_area_appeal(coordinator).sent == 0

    def test_a_released_caretaker_is_not_written_to(self, area):
        from django.utils import timezone

        coordinator, mine, _ = area
        volunteer = caretaker_in(mine, "Była opiekunka")
        volunteer.assignments.update(ended_at=timezone.now())

        assert send_area_appeal(coordinator).sent == 0


class TestTheDailyLimit:
    def test_somebody_already_written_to_today_is_skipped(self, area):
        coordinator, mine, _ = area
        anna = caretaker_in(mine, "Anna")
        EmailLog.objects.create(user=anna, subject="poranny digest", ok=True)

        result = send_area_appeal(coordinator)

        assert result.sent == 0
        assert result.skipped == 1
        assert mail.outbox == []

    def test_the_coordinator_is_told_how_far_it_reached(self, area):
        """The number is the point: silence would look like success."""
        coordinator, mine, _ = area
        reached = caretaker_in(mine, "Anna")
        missed = caretaker_in(mine, "Marta")
        EmailLog.objects.create(user=missed, subject="poranny digest", ok=True)

        result = send_area_appeal(coordinator)

        assert (result.sent, result.skipped) == (1, 1)
        assert [m.to for m in mail.outbox] == [[reached.email]]

    def test_a_failed_attempt_does_not_use_up_the_day(self, area):
        coordinator, mine, _ = area
        anna = caretaker_in(mine, "Anna")
        EmailLog.objects.create(user=anna, subject="nieudana próba", ok=False)

        assert send_area_appeal(coordinator).sent == 1

    def test_every_send_is_logged(self, area):
        coordinator, mine, _ = area
        anna = caretaker_in(mine, "Anna")

        send_area_appeal(coordinator)

        assert EmailLog.objects.filter(user=anna, ok=True).exists()

    def test_the_appeal_blocks_todays_digest(self, area):
        """One e-mail a day means one, whichever came first."""
        from notifications.services import send_digests

        coordinator, mine, _ = area
        anna = caretaker_in(mine, "Anna")
        send_area_appeal(coordinator)
        mail.outbox.clear()

        send_digests()

        assert [m for m in mail.outbox if anna.email in m.to] == []


class TestContent:
    def test_says_what_needs_doing(self, area):
        coordinator, mine, _ = area
        caretaker_in(mine, "Anna")

        send_area_appeal(coordinator)

        body = mail.outbox[0].body
        assert "Sierpc" in body
        assert "drzewa.greeninnowacje.pl" in body, "Link do mapy albo do moich drzew"

    def test_tone_is_an_invitation(self, area):
        """Spec §5.3: motivating, never reproachful."""
        coordinator, mine, _ = area
        caretaker_in(mine, "Anna")

        send_area_appeal(coordinator)

        lowered = mail.outbox[0].body.lower()
        for blaming in ("zaniedb", "zapomnia", "musisz"):
            assert blaming not in lowered

    def test_has_an_html_part_too(self, area):
        coordinator, mine, _ = area
        caretaker_in(mine, "Anna")

        send_area_appeal(coordinator)

        assert mail.outbox[0].alternatives[0][1] == "text/html"


class TestFromThePage:
    def test_button_sends_and_reports(self, client, area):
        coordinator, mine, _ = area
        caretaker_in(mine, "Anna")
        client.force_login(coordinator)

        response = client.post(APPEAL_URL, follow=True)

        assert len(mail.outbox) == 1
        assert any(m.level_tag == "success" for m in response.context["messages"])

    def test_the_message_names_the_numbers(self, client, area):
        coordinator, mine, _ = area
        caretaker_in(mine, "Anna")
        missed = caretaker_in(mine, "Marta")
        EmailLog.objects.create(user=missed, subject="digest", ok=True)
        client.force_login(coordinator)

        response = client.post(APPEAL_URL, follow=True)

        text = " ".join(str(m) for m in response.context["messages"])
        assert "1" in text and "2" in text, "Ilu dostało z ilu — inaczej cisza wygląda na sukces"

    def test_nobody_to_write_to_is_said_plainly(self, client, area):
        coordinator, _, _ = area
        client.force_login(coordinator)

        response = client.post(APPEAL_URL, follow=True)

        assert response.status_code == 200
        assert mail.outbox == []

    def test_rate_limited(self, client, settings, area):
        """The button must not become a transmitter."""
        settings.APPEAL_RATE_LIMIT = "1/d"
        coordinator, mine, _ = area
        caretaker_in(mine, "Anna")
        client.force_login(coordinator)
        client.post(APPEAL_URL)
        mail.outbox.clear()

        response = client.post(APPEAL_URL, follow=True)

        assert mail.outbox == []
        assert any(m.level_tag == "error" for m in response.context["messages"])

    def test_volunteer_cannot_send_an_appeal(self, client):
        client.force_login(UserFactory())

        assert client.post(APPEAL_URL).status_code == 403

    def test_get_does_not_send(self, client, area):
        coordinator, _, _ = area
        client.force_login(coordinator)

        assert client.get(APPEAL_URL).status_code == 405

    def test_the_button_is_on_the_overview(self, client, area):
        coordinator, mine, _ = area
        caretaker_in(mine, "Anna")
        client.force_login(coordinator)

        content = client.get(reverse("coordinator:overview")).content.decode()

        assert APPEAL_URL in content
