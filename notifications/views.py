from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Notification
from .selectors import for_user


@login_required
def notification_list(request):
    """The notices screen (UI doc §8.8): newest first, unread marked apart.

    Read ones stay — the list is a history of what happened to the trees in this person's
    care, not an inbox to be emptied.
    """
    return render(request, "notifications/list.html", {"notifications": for_user(request.user)})


@require_POST
@login_required
def open_notification(request, notification_id):
    """Mark one notice read and go to the tree it is about.

    A POST rather than a link, although a link would read better: everything else in this
    codebase changes state through POST, and a prefetching browser must not be able to mark
    somebody's notices read on their behalf.
    """
    # Scoped inside the lookup, so somebody else's id is a 404 rather than a separate
    # permission check that a later edit could forget.
    notification = get_object_or_404(Notification, pk=notification_id, user=request.user)
    if notification.is_unread:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])
    return redirect("trees:card", tree_id=notification.tree_id)


@require_POST
@login_required
def mark_all_read(request):
    """Clear the badge in one go, then back to the list."""
    cleared = Notification.objects.filter(user=request.user, read_at__isnull=True).update(
        read_at=timezone.now()
    )
    if cleared:
        messages.success(request, "Oznaczono wszystkie jako przeczytane.")
    return redirect("notifications:list")
