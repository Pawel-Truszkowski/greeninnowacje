from django.shortcuts import render

from accounts.permissions import coordinator_localities, coordinator_required

from .selectors import area_stats, area_trees, area_volunteers


@coordinator_required
def overview(request):
    """Area overview (UI doc §8.9): stats, trees most urgent first, volunteers."""
    localities = coordinator_localities(request.user)
    context = {
        "localities": localities,
        "stats": area_stats(request.user),
        "trees": area_trees(request.user),
        "volunteers": area_volunteers(request.user),
    }
    return render(request, "coordinator/overview.html", context)
