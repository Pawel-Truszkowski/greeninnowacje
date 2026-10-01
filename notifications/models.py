from django.conf import settings
from django.db import models
from django.utils import timezone


class EmailLog(models.Model):
    """E-mail delivery log; backs the "max 1 e-mail per user per day" rule (spec §5.3)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    subject = models.CharField(max_length=255, blank=True)
    sent_at = models.DateTimeField(default=timezone.now)
    ok = models.BooleanField(null=True)

    class Meta:
        db_table = "email_log"
        verbose_name = "wysłany e-mail"
        verbose_name_plural = "wysłane e-maile"
        indexes = [models.Index(fields=["user", "-sent_at"], name="email_log_user_idx")]

    def __str__(self):
        return f"{self.sent_at:%Y-%m-%d %H:%M} {self.subject}"


class Notification(models.Model):
    """Something a user should see in the app (UI doc §8.8, architecture doc §8).

    Deliberately not a by-product of sending e-mail. A mailbox tolerates one message a day
    (spec §5.3) and that limit shapes `send_digests`; a list tolerates ten, so these are
    created when the thing happens — a tree turning URGENT — rather than when the morning
    post goes out.

    When Web Push arrives it will send what is already stored here instead of working the
    recipients out a second time.
    """

    class Kind(models.TextChoices):
        URGENT = "urgent", "Drzewo wymaga podlania"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="notifications"
    )
    tree = models.ForeignKey("trees.Tree", on_delete=models.PROTECT, related_name="notifications")
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.URGENT)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notifications"
        verbose_name = "powiadomienie"
        verbose_name_plural = "powiadomienia"
        ordering = ["-created_at"]
        indexes = [
            # The list and the unread badge both walk this, which is why `read_at` sits
            # between the owner and the ordering column.
            models.Index(fields=["user", "read_at", "-created_at"], name="notifications_user_idx"),
        ]

    def __str__(self):
        return f"{self.user_id}: {self.get_kind_display()} ({self.tree_id})"

    @property
    def is_unread(self):
        return self.read_at is None
