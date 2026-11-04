from django.conf import settings
from django.db import models
from django.utils import timezone

from .rules import BADGES_BY_CODE


class UserBadge(models.Model):
    """A badge somebody earned. Points and levels are computed; badges are kept.

    Kept because a badge, once earned, stays — even if the photo behind it is later removed —
    and because "when" and "already seen" have to live somewhere. The catalogue itself is
    code (`rules.BADGES`); only the code is stored, so wording can change without a migration.
    """

    # CASCADE: derived data — unlike waterings, nothing here is evidence of anything.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="badges"
    )
    code = models.CharField("odznaka", max_length=32)
    awarded_at = models.DateTimeField("zdobyta", default=timezone.now)
    # NULL until the person has been told — drives the one-off "Nowa odznaka!" message.
    seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "user_badges"
        verbose_name = "odznaka użytkownika"
        verbose_name_plural = "odznaki użytkowników"
        ordering = ["awarded_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "code"], name="one_badge_per_user"),
        ]

    def __str__(self):
        return f"{self.user} — {self.badge.name if self.badge else self.code}"

    @property
    def badge(self):
        """The catalogue entry; None for a code that was retired from `rules.BADGES`."""
        return BADGES_BY_CODE.get(self.code)
