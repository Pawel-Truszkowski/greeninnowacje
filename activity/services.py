"""The one place that writes activity events.

Callers pass whatever they have; an anonymous user becomes NULL, so a view never has to
remember the difference between `AnonymousUser` and "nobody".
"""

from .models import ActivityEvent


def record(kind, *, user=None, tree=None):
    if user is not None and not user.is_authenticated:
        user = None
    return ActivityEvent.objects.create(kind=kind, user=user, tree=tree)
