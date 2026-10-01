from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import User
from accounts.permissions import coordinator_localities, coordinator_required
from core.ratelimit import rate_limit
from notifications.services import send_area_appeal
from trees.models import Tree
from trees.services import (
    CaretakerConflict,
    OutsideArea,
    assign_caretaker_for,
    release_caretaker_of,
)

from .selectors import area_stats, area_trees, area_volunteers


def assignable_volunteers():
    """Everyone a coordinator may put in charge of a tree.

    Deliberately not limited to people already active in the area: finding a caretaker where
    there is none is the job, so the list has to reach beyond the people already doing it.
    Inactive accounts are out — they could not act on a tree they were given.
    """
    return User.objects.filter(is_active=True).order_by("display_name")


@coordinator_required
def overview(request):
    """Area overview (UI doc §8.9): stats, trees most urgent first, volunteers."""
    localities = coordinator_localities(request.user)
    context = {
        "localities": localities,
        "stats": area_stats(request.user),
        "trees": area_trees(request.user),
        "volunteers": area_volunteers(request.user),
        "assignable": assignable_volunteers(),
    }
    return render(request, "coordinator/overview.html", context)


def _area_tree(tree_id):
    """404 rather than an exception for a tree that is archived or does not exist."""
    return get_object_or_404(Tree, pk=tree_id, lifecycle=Tree.Lifecycle.ACTIVE)


@require_POST
@coordinator_required
def assign(request, tree_id):
    """Put the chosen volunteer in charge of a tree in the area, then back to the overview."""
    tree = _area_tree(tree_id)
    volunteer_id = request.POST.get("volunteer")
    if not volunteer_id:
        messages.error(request, "Wybierz wolontariusza z listy.")
        return redirect("coordinator:overview")

    volunteer = get_object_or_404(User, pk=volunteer_id, is_active=True)
    try:
        assign_caretaker_for(tree, volunteer, by=request.user)
    except (OutsideArea, CaretakerConflict) as problem:
        messages.error(request, str(problem))
    else:
        messages.success(
            request, f"{volunteer.display_name} opiekuje się teraz drzewem: {tree.species}."
        )
    return redirect("coordinator:overview")


@require_POST
@coordinator_required
def release(request, tree_id):
    """End the current assignment on a tree in the area."""
    tree = _area_tree(tree_id)
    try:
        released = release_caretaker_of(tree, by=request.user)
    except OutsideArea as problem:
        messages.error(request, str(problem))
    else:
        messages.success(
            request,
            f"Drzewo {tree.species} czeka na nowego opiekuna."
            if released
            else f"Drzewo {tree.species} i tak nie miało opiekuna.",
        )
    return redirect("coordinator:overview")


@require_POST
@coordinator_required
@rate_limit("appeal", lambda: settings.APPEAL_RATE_LIMIT, key="user")
def appeal(request):
    """„📣 Poproś wolontariuszy o pomoc" (PoC). Tells the coordinator how far it reached."""
    if request.limited:
        messages.error(request, "Apel wysłano już dziś kilka razy. Spróbuj jutro.")
        return redirect("coordinator:overview")

    result = send_area_appeal(request.user)
    total = result.sent + result.skipped
    if not total:
        messages.info(
            request, "Nie ma jeszcze komu wysłać apelu — w obszarze nikt nie opiekuje się drzewem."
        )
    elif result.skipped:
        # Both numbers on purpose: silence would look like success.
        messages.success(
            request,
            f"Apel wysłano do {result.sent} z {total} wolontariuszy — "
            f"pozostali dostali już dziś wiadomość.",
        )
    else:
        messages.success(request, f"Apel wysłano do {result.sent} wolontariuszy. Dziękujemy!")
    return redirect("coordinator:overview")
