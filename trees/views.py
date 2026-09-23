from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from core.ratelimit import rate_limit

from .models import Locality, Tree
from .selectors import extended_tree_card, public_tree_card
from .services import (
    CaretakerConflict,
    assign_caretaker,
    caretaker_of,
    days_since,
    humanized_days,
    my_trees,
    record_watering,
    release_caretaker,
)
from .status_display import status_labels

WATERING_THANKS = "Dziękujemy! Drzewo zostało podlane 🌱"


@ensure_csrf_cookie
def map_view(request):
    """Public map (UI doc §8.1). Data is fetched by static/js/map.js from /api/trees."""
    localities = Locality.objects.annotate(
        tree_count=Count("trees", filter=Q(trees__lifecycle=Tree.Lifecycle.ACTIVE))
    ).filter(tree_count__gt=0)
    context = {
        "localities": localities,
        "map_config": {
            "tilesUrl": settings.MAP_TILES_URL,
            "attribution": settings.MAP_ATTRIBUTION,
            "statuses": status_labels(),
        },
    }
    return render(request, "trees/map.html", context)


def tree_card(request, tree_id):
    """Tree card: public by default, extended for logged-in users (spec §4)."""
    tree = get_object_or_404(Tree.objects.select_related("locality"), pk=tree_id)
    if request.user.is_authenticated:
        card = extended_tree_card(tree)
        caretaker = caretaker_of(tree)
        context = {
            "card": card,
            "tree": tree,
            "is_my_tree": caretaker == request.user,
            "has_caretaker": caretaker is not None,
        }
    else:
        context = {"card": public_tree_card(tree), "tree": tree}
    return render(request, "trees/tree_card.html", context)


def _active_tree(tree_id):
    return get_object_or_404(Tree, pk=tree_id, lifecycle=Tree.Lifecycle.ACTIVE)


def _back_to(request, tree):
    """Return to the list when watering from 'Moje drzewa', else to the card."""
    if request.POST.get("from") == "list":
        return redirect("trees:my")
    return redirect("trees:card", tree_id=tree.pk)


@require_POST
@login_required
@rate_limit("watering", lambda: settings.WATERING_RATE_LIMIT, key="user")
def water_tree(request, tree_id):
    tree = _active_tree(tree_id)
    if request.limited:
        messages.error(request, "Za dużo zgłoszeń podlania. Spróbuj za chwilę.")
        return _back_to(request, tree)
    record_watering(tree, request.user)
    messages.success(request, WATERING_THANKS)
    return _back_to(request, tree)


@require_POST
@login_required
def take_care(request, tree_id):
    tree = _active_tree(tree_id)
    try:
        assign_caretaker(tree, request.user)
    except CaretakerConflict as conflict:
        messages.error(request, str(conflict))
    else:
        messages.success(request, "Dziękujemy! Opiekujesz się tym drzewem 💚")
    return redirect("trees:card", tree_id=tree.pk)


@require_POST
@login_required
def stop_care(request, tree_id):
    tree = get_object_or_404(Tree, pk=tree_id)
    if release_caretaker(tree, request.user):
        messages.success(request, "Opieka zakończona. Dzięki za dotychczasową pomoc!")
    return redirect("trees:card", tree_id=tree.pk)


@login_required
def my_trees_view(request):
    """'Moje drzewa' (UI doc §8.7): most urgent first, watering straight from the list."""
    trees = [
        {
            "tree": tree,
            "last_watered": humanized_days(days_since(tree.last_watered_at)),
        }
        for tree in my_trees(request.user)
    ]
    return render(request, "trees/my_trees.html", {"trees": trees})
