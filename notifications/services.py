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
from .selectors import (
    active_admins,
    active_coordinators,
    admin_overview,
    area_volunteer_emails,
    coordinator_overview,
    urgent_by_caretaker,
)

VOLUNTEER_TEMPLATE = "volunteer_urgent"
ADMIN_TEMPLATE = "admin_digest"
VOLUNTEER_SUBJECT = "Twoje drzewa czekają na Ciebie 💧"
ADMIN_SUBJECT = "Drzewa wymagające podlania — {day:%d.%m.%Y}"
COORDINATOR_TEMPLATE = "coordinator_digest"
COORDINATOR_SUBJECT = "{area}: drzewa wymagające podlania — {day:%d.%m.%Y}"
APPEAL_TEMPLATE = "area_appeal"
APPEAL_SUBJECT = "Drzewa w okolicy {area} czekają na wodę 💧"


@dataclass(frozen=True)
class Digest:
    """One planned e-mail. Building it touches no SMTP, so a plan can be asserted in tests."""

    user: object
    template: str
    subject: str
    context: dict


@dataclass(frozen=True)
class AppealResult:
    """What the coordinator is told: how many heard the appeal, and how many had already
    had their one e-mail for the day."""

    sent: int = 0
    skipped: int = 0
    failed: int = 0


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


def coordinator_digest(user, overview, my_trees, today):
    """The area digest. Same shape as `admin_digest`, narrowed to the coordinator's area."""
    area = ", ".join(row["name"] for row in overview["localities"])
    return Digest(
        user=user,
        template=COORDINATOR_TEMPLATE,
        subject=COORDINATOR_SUBJECT.format(area=area, day=today),
        context={
            "name": user.display_name,
            "today": today,
            "area": area,
            "my_trees": tree_rows(my_trees),
            "localities": overview["localities"],
            "orphans": tree_rows(overview["orphans"]),
            "urgent_total": overview["urgent_total"],
            "area_url": _absolute("coordinator:overview"),
        },
    )


def send_area_appeal(coordinator, today=None):
    """„📣 Poproś wolontariuszy o pomoc" from the area overview. Returns an `AppealResult`.

    Respects the one-e-mail-a-day rule (spec §5.3) — it is unconditional, and an appeal is
    not an exception to it. Which is why the result reports `skipped` as well as `sent`: a
    coordinator who does not know their appeal reached three people out of eight is worse off
    than one who does.
    """
    today = today or timezone.localdate()
    overview = coordinator_overview(coordinator)
    recipients = list(area_volunteer_emails(coordinator))
    if not recipients:
        return AppealResult()

    blocked = already_sent_today([person.pk for person in recipients], today)
    due = [person for person in recipients if person.pk not in blocked]
    area = ", ".join(row["name"] for row in overview["localities"]) or "Twoja okolica"

    sent = failed = 0
    with get_connection() as connection:
        for person in due:
            digest = Digest(
                user=person,
                template=APPEAL_TEMPLATE,
                subject=APPEAL_SUBJECT.format(area=area),
                context={
                    "name": person.display_name,
                    "area": area,
                    "from_name": coordinator.display_name,
                    "orphans": tree_rows(overview["orphans"]),
                    "urgent_total": overview["urgent_total"],
                    "my_trees_url": _absolute("trees:my"),
                },
            )
            message = render(digest)
            try:
                delivered = bool(connection.send_messages([message]))
            except OSError:
                delivered = False
            EmailLog.objects.create(user=person, subject=message.subject, ok=delivered)
            sent += int(delivered)
            failed += int(not delivered)

    return AppealResult(sent=sent, skipped=len(recipients) - len(due), failed=failed)


def plan_digests(today, urgent, overview, admins, areas):
    """Decide who gets an e-mail today and which one — at most one `Digest` per user.

    A pure function, like `trees/status.py`: the caller does the querying, so the rule
    "who gets what" can be tested on plain dicts and lists.

    Arguments:
      `today`    — the date in the admin subject line.
      `urgent`   — `{user: [tree, …]}`, caretakers of URGENT trees (`urgent_by_caretaker()`).
      `overview` — `{"localities": […], "orphans": […], "urgent_total": int}`
                   (`admin_overview()`); `urgent_total == 0` means nothing needs water.
      `admins`   — `[user, …]` who should get the summary (`active_admins()`).
      `areas`    — `[(coordinator, their own overview), …]`; each is checked separately,
                   because a quiet area deserves no e-mail even on a day the rest is on fire.

    Builders ready to use: `volunteer_digest(user, trees)`,
    `admin_digest(user, overview, my_trees, today)` and `coordinator_digest(...)` — the last
    two skip their personal section when `my_trees` is empty.

    Still at most one `Digest` per user, so a coordinator who also looks after an urgent tree
    gets their own trees inside the area digest rather than a second e-mail.
    """
    digests = []
    # Copy, because popping below must not empty the caller's dict.
    caretakers = dict(urgent)

    if overview["urgent_total"]:
        for admin in admins:
            # pop() does both jobs at once: it hands over the admin's own urgent trees and
            # takes them out of the volunteer pool, so nobody is written to twice.
            digests.append(admin_digest(admin, overview, caretakers.pop(admin, []), today))

    for person, area in areas:
        # Checked per area: a quiet one earns no e-mail even on a day the rest is on fire.
        # A coordinator whose area is quiet stays in the pool below, because their own urgent
        # tree somewhere else is still their business as a volunteer.
        if area["urgent_total"]:
            digests.append(coordinator_digest(person, area, caretakers.pop(person, []), today))

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
    planned = plan_digests(
        today,
        dict(urgent_by_caretaker()),
        admin_overview(),
        active_admins(),
        [(person, coordinator_overview(person)) for person in active_coordinators()],
    )
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
