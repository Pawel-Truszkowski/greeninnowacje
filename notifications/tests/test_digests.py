"""Daily digest e-mails (spec §5.3). Written before the implementation.

The two rules worth protecting with tests are the ones a reader cannot see in the code at a
glance: a user never gets two e-mails on the same day, and a failed delivery does not use up
that day's allowance — otherwise one SMTP outage at 07:30 silences the whole day.
"""

from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from factories import LocalityFactory, TreeFactory, UserFactory
from notifications.models import EmailLog
from notifications.services import send_digests
from trees.models import Tree
from trees.tests.factories import assign

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _locmem(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.APP_BASE_URL = "https://drzewa.greeninnowacje.pl"


def urgent_tree(**kwargs):
    return TreeFactory(status=Tree.Status.URGENT, **kwargs)


def sent_to(email):
    return [message for message in mail.outbox if email in message.to]


class TestVolunteerDigest:
    def test_caretaker_of_an_urgent_tree_gets_an_email(self):
        volunteer = UserFactory()
        tree = urgent_tree()
        assign(tree, volunteer)

        result = send_digests()

        assert result.sent == 1
        message = sent_to(volunteer.email)[0]
        assert "Twoje drzewa czekają na Ciebie" in message.subject
        assert tree.species in message.body
        assert str(tree.pk) in message.body

    def test_email_links_to_the_card_with_the_public_base_url(self):
        volunteer = UserFactory()
        tree = urgent_tree()
        assign(tree, volunteer)

        send_digests()

        assert (
            f"https://drzewa.greeninnowacje.pl/drzewo/{tree.pk}" in sent_to(volunteer.email)[0].body
        )

    def test_only_own_urgent_trees_are_listed(self):
        mine, theirs = UserFactory(), UserFactory()
        my_tree, their_tree = urgent_tree(), urgent_tree()
        assign(my_tree, mine)
        assign(their_tree, theirs)

        send_digests()

        body = sent_to(mine.email)[0].body
        assert str(my_tree.pk) in body
        assert str(their_tree.pk) not in body

    def test_healthy_trees_do_not_trigger_an_email(self):
        volunteer = UserFactory()
        assign(TreeFactory(status=Tree.Status.SOON), volunteer)

        assert send_digests().sent == 0
        assert mail.outbox == []

    def test_archived_tree_is_ignored(self):
        volunteer = UserFactory()
        assign(urgent_tree(lifecycle=Tree.Lifecycle.ARCHIVED), volunteer)

        send_digests()

        assert sent_to(volunteer.email) == []

    def test_released_caretaker_is_not_written_to(self):
        volunteer = UserFactory()
        assignment = assign(urgent_tree(), volunteer)
        assignment.ended_at = timezone.now()
        assignment.save()

        send_digests()

        assert sent_to(volunteer.email) == []

    def test_inactive_user_is_skipped(self):
        volunteer = UserFactory(is_active=False)
        assign(urgent_tree(), volunteer)

        send_digests()

        assert sent_to(volunteer.email) == []


class TestAdminDigest:
    def test_admin_gets_counts_and_orphans(self):
        admin = UserFactory(role="admin")
        locality = LocalityFactory(name="Sierpc")
        orphan = urgent_tree(locality=locality)
        assign(urgent_tree(locality=locality), UserFactory())

        send_digests()

        body = sent_to(admin.email)[0].body
        assert "Sierpc" in body
        assert str(orphan.pk) in body, "Digest musi wyróżniać drzewa bez opiekuna"

    def test_admin_is_not_written_to_when_nothing_is_urgent(self):
        UserFactory(role="admin")
        TreeFactory(status=Tree.Status.OK)

        assert send_digests().sent == 0
        assert mail.outbox == []

    def test_admin_who_is_a_caretaker_gets_exactly_one_email(self):
        admin = UserFactory(role="admin")
        tree = urgent_tree()
        assign(tree, admin)

        send_digests()

        messages = sent_to(admin.email)
        assert len(messages) == 1, "Limit 1 e-mail dziennie obowiązuje też administratora"
        assert str(tree.pk) in messages[0].body, "Własne drzewa nie mogą wypaść z maila"

    def test_admin_digest_reveals_no_personal_data(self):
        """Spec §7: a digest may be forwarded on — it carries numbers, not people.

        Only the admin's copy is inspected: the volunteer's own e-mail greets them by name,
        which is their own data, not a leak.
        """
        admin = UserFactory(role="admin")
        caretaker = UserFactory(display_name="Jan Kowalski", email="jan.kowalski@przyklad.pl")
        assign(urgent_tree(), caretaker)

        send_digests()

        for message in sent_to(admin.email):
            body = message.body + "".join(part for part, _ in message.alternatives)
            assert caretaker.email not in body
            assert caretaker.display_name not in body


class TestDailyLimit:
    def test_second_run_on_the_same_day_sends_nothing(self):
        volunteer = UserFactory()
        assign(urgent_tree(), volunteer)

        first = send_digests()
        second = send_digests()

        assert (first.sent, second.sent) == (1, 0)
        assert second.skipped == 1
        assert len(mail.outbox) == 1

    def test_yesterdays_email_does_not_block_today(self):
        volunteer = UserFactory()
        assign(urgent_tree(), volunteer)
        EmailLog.objects.create(
            user=volunteer, subject="wczoraj", ok=True, sent_at=timezone.now() - timedelta(days=1)
        )

        assert send_digests().sent == 1

    def test_failed_delivery_does_not_use_up_the_allowance(self):
        volunteer = UserFactory()
        assign(urgent_tree(), volunteer)
        EmailLog.objects.create(user=volunteer, subject="nieudana próba", ok=False)

        assert send_digests().sent == 1

    def test_force_ignores_the_limit(self):
        volunteer = UserFactory()
        assign(urgent_tree(), volunteer)
        send_digests()

        assert send_digests(force=True).sent == 1
        assert len(mail.outbox) == 2

    def test_every_send_is_logged(self):
        volunteer = UserFactory()
        assign(urgent_tree(), volunteer)

        send_digests()

        log = EmailLog.objects.get(user=volunteer)
        assert log.ok is True
        assert log.subject


class TestDryRun:
    def test_dry_run_sends_nothing_and_logs_nothing(self):
        volunteer = UserFactory()
        assign(urgent_tree(), volunteer)

        result = send_digests(dry_run=True)

        assert result.sent == 1, "Próba raportuje, ile maili by poszło"
        assert mail.outbox == []
        assert not EmailLog.objects.exists()

    def test_dry_run_leaves_the_real_run_possible(self):
        volunteer = UserFactory()
        assign(urgent_tree(), volunteer)

        send_digests(dry_run=True)

        assert send_digests().sent == 1


class TestCommand:
    def test_command_reports_what_it_did(self, capsys):
        from django.core.management import call_command

        volunteer = UserFactory()
        assign(urgent_tree(), volunteer)

        call_command("send_digests")

        out = capsys.readouterr().out
        assert "Wysłano 1" in out

    def test_command_dry_run_is_marked_as_such(self, capsys):
        from django.core.management import call_command

        call_command("send_digests", "--dry-run")

        assert "[próba]" in capsys.readouterr().out
