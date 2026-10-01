from .selectors import unread_count


def unread_notifications(request):
    """The badge in the navigation, on every page there is.

    The only part of this feature that costs something on every request, so it costs it only
    for signed-in users and only once: a single count, no objects loaded. Anonymous visitors
    get nothing and pay nothing.

    Must return a dict — Django renders nothing at all if a context processor returns
    anything else, which would turn a missing badge into a blank application.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    return {"unread_notifications": unread_count(user)}
