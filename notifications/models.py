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
