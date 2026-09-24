import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone


class Locality(models.Model):
    """Locality — the unit weather is fetched for (centroid = lat/lng)."""

    name = models.CharField(max_length=120)
    lat = models.DecimalField(max_digits=9, decimal_places=6)
    lng = models.DecimalField(max_digits=9, decimal_places=6)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        db_table = "localities"
        verbose_name = "miejscowość"
        verbose_name_plural = "miejscowości"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="localities_name_ci_unique"),
        ]

    def __str__(self):
        return self.name


class TreeSpecies(models.Model):
    """Catalogue behind the species dropdown in the registration form.

    `Tree.species` stays a text column (spec §3) — the catalogue curates what volunteers
    can pick, without rewriting history or blocking an unusual planting ("Inny" option).
    Retired species keep `is_active=False` instead of being deleted.
    """

    name = models.CharField("nazwa", max_length=120)
    is_active = models.BooleanField("aktywny", default=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        db_table = "tree_species"
        verbose_name = "gatunek drzewa"
        verbose_name_plural = "gatunki drzew"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="tree_species_name_ci_unique"),
        ]

    def __str__(self):
        return self.name


class Tree(models.Model):
    class Status(models.TextChoices):
        OK = "OK", "Podlane"
        SOON = "SOON", "Wkrótce podlać"
        URGENT = "URGENT", "Pilnie podlać"

    class Lifecycle(models.TextChoices):
        ACTIVE = "active", "Aktywne"
        ARCHIVED = "archived", "Zarchiwizowane"

    # UUID on purpose: permanent public URL /drzewo/{uuid} that doesn't reveal the tree count.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lat = models.DecimalField(max_digits=9, decimal_places=6)
    lng = models.DecimalField(max_digits=9, decimal_places=6)
    gps_accuracy_m = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    locality = models.ForeignKey(Locality, on_delete=models.PROTECT, related_name="trees")
    species = models.CharField("gatunek", max_length=120)
    planted_on = models.DateField("data posadzenia", default=timezone.localdate)
    planted_by = models.CharField("kto sadził", max_length=200, blank=True)
    notes = models.TextField("notatki", max_length=2000, blank=True)
    # Unused in the MVP; nullable per the schema contract (spec §3).
    photo_url = models.URLField(null=True, blank=True)  # noqa: DJ001
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.OK)
    lifecycle = models.CharField(max_length=10, choices=Lifecycle.choices, default=Lifecycle.ACTIVE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_trees"
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        db_table = "trees"
        verbose_name = "drzewo"
        verbose_name_plural = "drzewa"
        indexes = [
            models.Index(
                fields=["status"], name="trees_status_idx", condition=Q(lifecycle="active")
            ),
        ]

    def __str__(self):
        return f"{self.species} ({self.locality})"


class AppendOnlyError(Exception):
    pass


class WateringQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise AppendOnlyError("Wpisy podlewania są niezmienne (append-only).")

    def delete(self):
        raise AppendOnlyError("Wpisy podlewania są niezmienne (append-only).")


class Watering(models.Model):
    """Watering history — APPEND-ONLY (audit requirement).

    Enforced twice: here in the ORM and by a PostgreSQL trigger (migration 0002),
    so not even raw SQL from the app can change or delete an entry.
    """

    tree = models.ForeignKey(Tree, on_delete=models.PROTECT, related_name="waterings")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="waterings"
    )
    watered_at = models.DateTimeField(default=timezone.now)

    objects = WateringQuerySet.as_manager()

    class Meta:
        db_table = "waterings"
        verbose_name = "podlanie"
        verbose_name_plural = "podlania"
        indexes = [models.Index(fields=["tree", "-watered_at"], name="waterings_tree_idx")]

    def __str__(self):
        return f"{self.tree_id} @ {self.watered_at:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AppendOnlyError("Wpisy podlewania są niezmienne (append-only).")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyError("Wpisy podlewania są niezmienne (append-only).")


class Assignment(models.Model):
    """A volunteer caring for a tree; ended_at IS NULL = active. At most one active per tree."""

    tree = models.ForeignKey(Tree, on_delete=models.PROTECT, related_name="assignments")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="assignments"
    )
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "assignments"
        verbose_name = "przypisanie"
        verbose_name_plural = "przypisania"
        constraints = [
            models.UniqueConstraint(
                fields=["tree"],
                condition=Q(ended_at__isnull=True),
                name="one_active_per_tree",
                violation_error_message="To drzewo ma już aktywnego opiekuna.",
            ),
        ]

    def __str__(self):
        return f"{self.user_id} → {self.tree_id}"
