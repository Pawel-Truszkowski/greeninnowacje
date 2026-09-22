import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    def get_by_natural_key(self, email):
        return self.get(email__iexact=email)

    def create_user(self, email, password, display_name, **extra):
        user = self.model(email=self.normalize_email(email), display_name=display_name, **extra)
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, display_name, **extra):
        extra.update(role=User.Role.ADMIN, is_staff=True, is_superuser=True)
        return self.create_user(email, password, display_name, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """Volunteer or administrator account (spec §3, table `users`).

    `is_staff`/`is_superuser` only gate the technical Django admin;
    permissions inside the app are derived from `role`.
    """

    class Role(models.TextChoices):
        VOLUNTEER = "volunteer", "Wolontariusz"
        ADMIN = "admin", "Administrator"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Stored lowercase (see save) — makes uniqueness case-insensitive.
    email = models.EmailField(
        "e-mail",
        max_length=254,
        unique=True,
        error_messages={"unique": "Konto z tym adresem e-mail już istnieje."},
    )
    display_name = models.CharField("imię lub pseudonim", max_length=60)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.VOLUNTEER)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["display_name"]

    class Meta:
        db_table = "users"
        verbose_name = "użytkownik"
        verbose_name_plural = "użytkownicy"

    def __str__(self):
        return f"{self.display_name} <{self.email}>"

    def clean(self):
        super().clean()
        self.email = self.email.strip().lower()

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    @property
    def is_app_admin(self):
        return self.role == self.Role.ADMIN
