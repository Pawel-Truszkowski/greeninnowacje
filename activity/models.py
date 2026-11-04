from django.conf import settings
from django.db import models
from django.utils import timezone


class ActivityEvent(models.Model):
    """One thing a person did: logged in, watered a tree, opened a public card.

    Deliberately thin — no IP, no user agent, no typed e-mail. The admin needs to know how
    the app is used, not to profile anybody (RODO), and `prune_activity` deletes old rows.
    Not append-only like `waterings`: retention is the reason this table exists in this form.
    """

    class Kind(models.TextChoices):
        LOGIN = "login", "Logowanie"
        LOGIN_FAILED = "login_failed", "Nieudane logowanie"
        LOGOUT = "logout", "Wylogowanie"
        SIGNUP = "signup", "Założenie konta"
        WATERING = "watering", "Podlanie"
        TREE_REGISTERED = "tree_registered", "Rejestracja drzewa"
        PHOTO_ADDED = "photo_added", "Dodanie zdjęcia"
        CARE_TAKEN = "care_taken", "Objęcie opieki"
        CARE_RELEASED = "care_released", "Oddanie opieki"
        CARD_VIEW = "card_view", "Wyświetlenie karty"

    kind = models.CharField("rodzaj", max_length=20, choices=Kind.choices)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="użytkownik",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="activity_events",
    )
    tree = models.ForeignKey(
        "trees.Tree",
        verbose_name="drzewo",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="activity_events",
    )
    created_at = models.DateTimeField("kiedy", default=timezone.now, db_index=True)

    class Meta:
        db_table = "activity_events"
        ordering = ["-created_at"]
        verbose_name = "zdarzenie"
        verbose_name_plural = "zdarzenia"
        indexes = [
            models.Index(fields=["kind", "created_at"], name="activity_kind_created"),
            models.Index(fields=["user", "created_at"], name="activity_user_created"),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} — {self.created_at:%Y-%m-%d %H:%M}"
