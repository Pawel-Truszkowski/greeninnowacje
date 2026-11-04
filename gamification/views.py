from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .selectors import achievements
from .services import award_badges, new_badges_message, take_unseen


def announce_new_badges(request):
    """After an action: one success toast for the badges it earned, if any."""
    message = new_badges_message(take_unseen(request.user))
    if message:
        messages.success(request, message)


@login_required
def achievements_view(request):
    """'Osiągnięcia': level, badges and the 30-day ranking.

    Awards first, so a badge earned with time alone (30 days of care) appears here. Badges
    are marked seen only after the page has read them, so they still carry "Nowa!" this once.
    """
    award_badges(request.user)
    context = achievements(request.user)
    take_unseen(request.user)
    return render(request, "gamification/achievements.html", context)
