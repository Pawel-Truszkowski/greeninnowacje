from django.conf import settings
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import ensure_csrf_cookie

from .models import Locality, Tree
from .selectors import public_tree_card
from .status_display import status_labels


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
    """Public tree card — the page a QR code leads to (UI doc §8.3)."""
    tree = get_object_or_404(Tree.objects.select_related("locality"), pk=tree_id)
    return render(request, "trees/tree_card.html", {"card": public_tree_card(tree)})
