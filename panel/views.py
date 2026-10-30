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
from education.models import SpeciesGuide
from education.services import save_guide, toggle_published
from education.views import guide_image_response
from trees.models import Tree, TreePhoto
from trees.services import delete_photo, recompute_all

from .forms import SpeciesGuideForm, ThresholdsForm, TreeAdminForm, UserAdminForm
from .selectors import ACTIVITY_DAYS, dashboard_stats, recent_photos


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


@app_admin_required
def export(request):
    """Download links for the CSV exports (spec §4). The files come from panel/export.py."""
    return render(request, "panel/export.html", {"tab": "export"})


@app_admin_required
def photos(request):
    return render(request, "panel/photos.html", {"photos": recent_photos(), "tab": "photos"})


@require_POST
@app_admin_required
def remove_photo(request, photo_id):
    """Moderation: remove a photo somebody asked about, or one that should not be there."""
    photo = get_object_or_404(TreePhoto, pk=photo_id)
    # Through the service, never queryset.delete() — that leaves the file on disk.
    delete_photo(photo, request.user)
    messages.success(request, "Zdjęcie zostało usunięte.")
    return redirect("panel:photos")


@app_admin_required
def species_list(request):
    guides = SpeciesGuide.objects.select_related("species")
    return render(request, "panel/species.html", {"guides": guides, "tab": "species"})


@app_admin_required
def add_species(request):
    return _species_form(request, SpeciesGuide())


@app_admin_required
def edit_species(request, guide_id):
    guide = get_object_or_404(SpeciesGuide.objects.select_related("species"), pk=guide_id)
    return _species_form(request, guide)


def _species_form(request, guide):
    adding = guide.pk is None
    form = SpeciesGuideForm(request.POST or None, request.FILES or None, instance=guide)
    if request.method == "POST" and form.is_valid():
        guide = save_guide(
            form.save(commit=False),
            form.cleaned_data["species"],
            infographic=form.cleaned_data["infographic"],
            photo=form.cleaned_data["photo"],
        )
        messages.success(
            request, f"{'Dodano' if adding else 'Zapisano'} opis gatunku: {guide.name}."
        )
        return redirect("panel:species")
    context = {"form": form, "guide": guide, "adding": adding, "tab": "species"}
    return render(request, "panel/species_form.html", context)


@require_POST
@app_admin_required
def toggle_species(request, guide_id):
    """Publish or hide — guides are not deleted, like trees (their species is PROTECTed)."""
    guide = toggle_published(get_object_or_404(SpeciesGuide, pk=guide_id))
    state = "opublikowany" if guide.is_published else "ukryty"
    messages.success(request, f"Opis gatunku {guide.name} jest teraz {state}.")
    return redirect("panel:species")


@app_admin_required
def species_image(request, guide_id, kind):
    """Preview for the panel: unlike the public URL, it shows hidden guides too."""
    response = guide_image_response(get_object_or_404(SpeciesGuide, pk=guide_id), kind)
    response["Cache-Control"] = "private, no-cache"
    return response
