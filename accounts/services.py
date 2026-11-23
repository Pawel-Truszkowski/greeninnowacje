"""Password reset — the one place both the HTML pages and /api/auth/* go through.

Django's own `PasswordResetForm.save()` builds the e-mailed link from the request's Host
header; behind a misconfigured proxy that lets an attacker plant their own domain in a real
reset e-mail. Links here are built from `APP_BASE_URL`, like every other e-mail we send.

Every outcome of `request_password_reset` looks the same from the outside (no account,
inactive account, per-address limit, SMTP failure): telling them apart would let anyone
probe which addresses have an account.
"""

import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from core.ratelimit import hit

from .models import User

logger = logging.getLogger(__name__)

SUBJECT = "Ustaw nowe hasło w GREENowacjach 🔑"
TEMPLATE = "password_reset"
# Per address, on top of the per-IP limit on the views: stops someone flooding a victim's
# inbox from many IPs. A legitimate user rarely needs more than one link.
PER_ADDRESS_RATE = "3/1h"


def reset_link(user):
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    path = reverse("accounts:password-reset-confirm", args=[uidb64, token])
    return f"{settings.APP_BASE_URL}{path}"


def _recipient(email):
    user = User.objects.filter(email__iexact=email, is_active=True).first()
    if user is None or not user.has_usable_password():
        return None
    return user


def request_password_reset(email):
    """E-mail a one-time link to set a new password, if `email` belongs to an active account.

    Never raises and returns nothing on purpose — see the module docstring.
    """
    email = (email or "").strip().lower()
    user = _recipient(email)
    if user is None or not hit(f"pwreset:{email}", PER_ADDRESS_RATE):
        return
    context = {
        "name": user.display_name,
        "url": reset_link(user),
        "valid_minutes": settings.PASSWORD_RESET_TIMEOUT // 60,
    }
    message = EmailMultiAlternatives(
        subject=SUBJECT,
        body=render_to_string(f"emails/{TEMPLATE}.txt", context),
        to=[user.email],
    )
    message.attach_alternative(render_to_string(f"emails/{TEMPLATE}.html", context), "text/html")
    # Not recorded in EmailLog: that table is the "one digest a day" allowance, and a reset
    # must neither use it up nor be blocked by it.
    try:
        message.send()
    except Exception:
        logger.exception("Password reset e-mail failed for user %s", user.pk)


def user_from_uid(uidb64):
    """The active account a reset link points at, or None for garbage / inactive accounts."""
    try:
        pk = urlsafe_base64_decode(uidb64).decode()
        return User.objects.get(pk=pk, is_active=True)
    # ValidationError: a well-encoded uid that is not a UUID.
    except TypeError, ValueError, OverflowError, ValidationError, User.DoesNotExist:
        return None


def user_from_reset_link(uidb64, token):
    user = user_from_uid(uidb64)
    if user is not None and default_token_generator.check_token(user, token):
        return user
    return None
