"""Admin panel pages (spec §4, path /admin/* reserved for this from day one).

Django's own admin stays available for developers; this panel is for the person running
the project — the four tabs the PoC showed and the client accepted.
"""

from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User
from accounts.permissions import app_admin_required
from trees.models import Tree
from trees.services import recompute_all

from .forms import ThresholdsForm, TreeAdminForm, UserAdminForm
from .selectors import ACTIVITY_DAYS, dashboard_stats


@app_admin_required
def dashboard(request):
    return render(request, "panel/dashboard.html", {"stats": dashboard_stats(), "tab": "stats"})


@app_admin_required
def thresholds(request):
    form = ThresholdsForm(request.POST or None, initial=ThresholdsForm.initial_from_config())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Progi zapisane. Zadziałają przy najbliższym przeliczeniu.")
        return redirect("panel:thresholds")
    return render(request, "panel/thresholds.html", {"form": form, "tab": "config"})


@require_POST
@app_admin_required
def recompute_now(request):
    """The "Przelicz statusy teraz" button from spec §6.2."""
    result = recompute_all()
    messages.success(
        request,
        f"Przeliczono {result.checked} drzew, zmieniono statusów: {result.changed}.",
    )
    return redirect("panel:thresholds")


@app_admin_required
def users(request):
    from datetime import timedelta

    month_ago = timezone.now() - timedelta(days=ACTIVITY_DAYS)
    people = User.objects.annotate(
        waterings_30=Count("waterings", filter=Q(waterings__watered_at__gte=month_ago))
    ).order_by("display_name")
    return render(request, "panel/users.html", {"users": people, "tab": "users"})


@app_admin_required
def edit_user(request, user_id):
    person = get_object_or_404(User, pk=user_id)
    form = UserAdminForm(request.POST or None, instance=person, editor=request.user)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, f"Zapisano zmiany dla: {person.display_name}.")
            return redirect("panel:users")
        for error in form.non_field_errors():
            messages.error(request, error)
    return render(request, "panel/user_form.html", {"form": form, "person": person, "tab": "users"})


@app_admin_required
def tree_list(request):
    trees = Tree.objects.select_related("locality").order_by("-created_at")
    status = request.GET.get("status")
    lifecycle = request.GET.get("lifecycle", Tree.Lifecycle.ACTIVE)
    locality = request.GET.get("locality")
    if status in Tree.Status.values:
        trees = trees.filter(status=status)
    if lifecycle in Tree.Lifecycle.values:
        trees = trees.filter(lifecycle=lifecycle)
    if locality and locality.isdigit():
        trees = trees.filter(locality_id=int(locality))

    context = {
        "trees": trees[:200],
        "statuses": Tree.Status.choices,
        "lifecycles": Tree.Lifecycle.choices,
        "filters": {"status": status or "", "lifecycle": lifecycle, "locality": locality or ""},
        "tab": "trees",
    }
    return render(request, "panel/trees.html", context)


@app_admin_required
def edit_tree(request, tree_id):
    tree = get_object_or_404(Tree.objects.select_related("locality"), pk=tree_id)
    form = TreeAdminForm(request.POST or None, instance=tree)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Zapisano zmiany w drzewie: {tree.species}.")
        return redirect("panel:trees")
    return render(request, "panel/tree_form.html", {"form": form, "tree": tree, "tab": "trees"})


@require_POST
@app_admin_required
def toggle_archive(request, tree_id):
    """Archive or restore — trees are never deleted (spec §3)."""
    tree = get_object_or_404(Tree, pk=tree_id)
    archiving = tree.lifecycle == Tree.Lifecycle.ACTIVE
    tree.lifecycle = Tree.Lifecycle.ARCHIVED if archiving else Tree.Lifecycle.ACTIVE
    tree.save(update_fields=["lifecycle"])
    messages.success(
        request,
        f"Drzewo {'zarchiwizowane' if archiving else 'przywrócone'}: {tree.species}.",
    )
    return redirect("panel:trees")
