"""Auth events from Django's signals, so the HTML pages and the JSON API share one mechanism.

`user_login_failed` carries the typed credentials; we keep none of them — people type their
password into the e-mail field, and naming the attacked account would confirm it exists.
"""

from django.conf import settings
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import ActivityEvent
from .services import record

Kind = ActivityEvent.Kind


@receiver(user_logged_in, dispatch_uid="activity_login")
def on_login(sender, request, user, **kwargs):
    record(Kind.LOGIN, user=user)


@receiver(user_login_failed, dispatch_uid="activity_login_failed")
def on_login_failed(sender, credentials, request=None, **kwargs):
    record(Kind.LOGIN_FAILED)


@receiver(user_logged_out, dispatch_uid="activity_logout")
def on_logout(sender, request, user, **kwargs):
    if user is not None:
        record(Kind.LOGOUT, user=user)


@receiver(post_save, sender=settings.AUTH_USER_MODEL, dispatch_uid="activity_signup")
def on_signup(sender, instance, created, raw=False, **kwargs):
    # On the model, not in the views: createsuperuser and seed_demo create accounts too.
    if created and not raw:
        record(Kind.SIGNUP, user=instance)
