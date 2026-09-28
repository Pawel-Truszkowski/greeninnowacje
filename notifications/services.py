"""Daily digest e-mails (spec §5.3; run at 07:30 by `deploy/crontab`, after the statuses).

Two rules shape everything here:

- **At most one e-mail per user per day.** So an admin who also looks after an urgent tree
  gets a single message carrying both sections, not two e-mails.
- **Only a delivered e-mail uses up that allowance.** A failure is logged with `ok=False`,
  so re-running the command after an SMTP outage finishes the job — spec §6 requires the
  scheduled jobs to be safe to repeat.
"""

from dataclasses import dataclass

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from trees.qr import tree_card_url

from .models import EmailLog
from .selectors import active_admins, admin_overview, urgent_by_caretaker

VOLUNTEER_TEMPLATE = "volunteer_urgent"
ADMIN_TEMPLATE = "admin_digest"
VOLUNTEER_SUBJECT = "Twoje drzewa czekają na Ciebie 💧"
ADMIN_SUBJECT = "Drzewa wymagające podlania — {day:%d.%m.%Y}"


@dataclass(frozen=True)
class Digest:
    """One planned e-mail. Building it touches no SMTP, so a plan can be asserted in tests."""

    user: object
    template: str
    subject: str
    context: dict


@dataclass(frozen=True)
class DigestResult:
    sent: int = 0
    skipped: int = 0
    failed: int = 0


def _absolute(name):
    """A link that still works when read in a mail client (spec §5.3: cards are linked)."""
    return f"{settings.APP_BASE_URL}{reverse(name)}"


def tree_rows(trees):
    """Trees flattened to what the templates render — including a clickable card link."""
    return [
        {
            "species": tree.species,
            "locality": tree.locality.name,
            "url": tree_card_url(tree.pk),
        }
        for tree in trees
    ]


def volunteer_digest(user, trees):
    return Digest(
        user=user,
        template=VOLUNTEER_TEMPLATE,
        subject=VOLUNTEER_SUBJECT,
        context={
            "name": user.display_name,
            "trees": tree_rows(trees),
            "my_trees_url": _absolute("trees:my"),
        },
    )


def admin_digest(user, overview, my_trees, today):
    """The admin's message. `my_trees` may be empty — then the personal section is skipped."""
    return Digest(
        user=user,
        template=ADMIN_TEMPLATE,
        subject=ADMIN_SUBJECT.format(day=today),
        context={
            "name": user.display_name,
            "today": today,
            "my_trees": tree_rows(my_trees),
            "localities": overview["localities"],
            "orphans": tree_rows(overview["orphans"]),
            "urgent_total": overview["urgent_total"],
            "panel_url": _absolute("panel:dashboard"),
        },
    )


def already_sent_today(user_ids, today):
    """Users who already have a delivered e-mail logged for `today` (spec §5.3 anti-spam).

    `sent_at__date` is resolved in `TIME_ZONE`, so "per day" means a Warsaw day — the same
    day the 07:30 job belongs to. A rolling 24-hour window would drift: a message sent at
    07:30 would block tomorrow's at 07:29.
    """
    return set(
        EmailLog.objects.filter(user_id__in=list(user_ids), ok=True, sent_at__date=today)
        .values_list("user_id", flat=True)
        .distinct()
    )


def plan_digests(today, urgent, overview, admins):
    """Decide who gets an e-mail today and which one — at most one `Digest` per user.

    A pure function, like `trees/status.py`: the caller does the querying, so the rule
    "who gets what" can be tested on plain dicts and lists.

    Arguments:
      `today`    — the date in the admin subject line.
      `urgent`   — `{user: [tree, …]}`, caretakers of URGENT trees (`urgent_by_caretaker()`).
      `overview` — `{"localities": […], "orphans": […], "urgent_total": int}`
                   (`admin_overview()`); `urgent_total == 0` means nothing needs water.
      `admins`   — `[user, …]` who should get the summary (`active_admins()`).

    Builders ready to use: `volunteer_digest(user, trees)` and
    `admin_digest(user, overview, my_trees, today)` — the latter skips its personal section
    when `my_trees` is empty.
    """
    digests = []
    # Copy, because popping below must not empty the caller's dict.
    caretakers = dict(urgent)

    if overview["urgent_total"]:
        for admin in admins:
            # pop() does both jobs at once: it hands over the admin's own urgent trees and
            # takes them out of the volunteer pool, so nobody is written to twice.
            digests.append(admin_digest(admin, overview, caretakers.pop(admin, []), today))

    digests += [volunteer_digest(user, trees) for user, trees in caretakers.items()]
    return digests


def render(digest):
    """A text body with an HTML alternative (spec §2: "szablony tekstowe + prosty HTML")."""
    message = EmailMultiAlternatives(
        subject=digest.subject,
        body=render_to_string(f"emails/{digest.template}.txt", digest.context),
        to=[digest.user.email],
    )
    message.attach_alternative(
        render_to_string(f"emails/{digest.template}.html", digest.context), "text/html"
    )
    return message


def send_digests(*, today=None, dry_run=False, force=False) -> DigestResult:
    today = today or timezone.localdate()
    planned = plan_digests(today, dict(urgent_by_caretaker()), admin_overview(), active_admins())
    if not planned:
        return DigestResult()

    blocked = set() if force else already_sent_today([d.user.pk for d in planned], today)
    due = [digest for digest in planned if digest.user.pk not in blocked]
    skipped = len(planned) - len(due)

    if dry_run:
        return DigestResult(sent=len(due), skipped=skipped)

    sent = failed = 0
    # One SMTP connection for the whole run, but `send_messages` is called per recipient:
    # it returns a count, so a batch of 20 with the answer 19 would not say whose e-mail
    # failed — and `EmailLog.ok` has to be true about one user, not about a batch.
    with get_connection() as connection:
        for digest in due:
            message = render(digest)
            try:
                delivered = bool(connection.send_messages([message]))
            except OSError:
                # smtplib raises subclasses of OSError; one bad address must not stop the
                # job, and the log below is what makes the retry pick it up tomorrow.
                delivered = False
            EmailLog.objects.create(user=digest.user, subject=message.subject, ok=delivered)
            sent += int(delivered)
            failed += int(not delivered)

    return DigestResult(sent=sent, skipped=skipped, failed=failed)
