from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, render

from accounts.permissions import coordinator_required, is_coordinator
from trees.qr import qr_png

from .models import SpeciesGuide
from .qr import species_page_url

# The URL names the image in Polish; the model field behind each name.
IMAGE_KINDS = {"infografika": "infographic", "miniatura": "photo"}


def published_guides():
    return SpeciesGuide.objects.filter(is_published=True).select_related("species")


def index(request):
    return render(request, "education/index.html", {"guides": published_guides()})


def species_detail(request, slug):
    # A handful of guides: loading them all is cheaper than two more queries for the pager.
    guides = list(published_guides())
    slugs = [guide.slug for guide in guides]
    if slug not in slugs:
        raise Http404
    i = slugs.index(slug)
    # Wraps around, so the pager never leads to a dead end.
    has_others = len(guides) > 1
    context = {
        "guide": guides[i],
        "previous": guides[i - 1] if has_others else None,
        "next": guides[(i + 1) % len(guides)] if has_others else None,
        # Coordinators and admins hand out saplings, so they print the sticker sheet.
        "can_print_stickers": is_coordinator(request.user),
    }
    return render(request, "education/species.html", context)


def species_image(request, slug, kind):
    """Public, unlike tree photos (`trees.views.tree_photo`): a guide is published content.

    The content type is fixed for the same reason as there — every stored image is a JPEG,
    and a constant plus the global `nosniff` leaves no room for content-type games. The URL
    carries `?v=<updated_at>`, so a day of caching never shows a replaced image.
    """
    if kind not in IMAGE_KINDS:
        raise Http404
    guide = get_object_or_404(SpeciesGuide, slug=slug, is_published=True)
    response = guide_image_response(guide, kind)
    response["Cache-Control"] = "public, max-age=86400"
    return response


def guide_image_response(guide, kind):
    """The file behind `kind`; shared with the panel preview, which also shows hidden guides."""
    field = IMAGE_KINDS.get(kind)
    if field is None:
        raise Http404
    return FileResponse(getattr(guide, field).open("rb"), content_type="image/jpeg")


# One A4 sheet: 3 columns × 4 rows.
STICKERS_PER_SHEET = 12
QR_CACHE_SECONDS = 86400


def species_qr(request, slug):
    """Public, like the page it points at — the code carries nothing but that URL.

    Hidden guides get a 404: a sticker leading to a missing page is a wasted print run.
    """
    guide = get_object_or_404(SpeciesGuide, slug=slug, is_published=True)
    response = HttpResponse(qr_png(species_page_url(guide)), content_type="image/png")
    response["Cache-Control"] = f"public, max-age={QR_CACHE_SECONDS}"
    if request.GET.get("download"):
        response["Content-Disposition"] = f'attachment; filename="qr-{guide.slug}.png"'
    return response


@coordinator_required
def species_stickers(request, slug):
    """A printable A4 sheet of stickers for saplings handed out to residents."""
    guide = get_object_or_404(SpeciesGuide, slug=slug, is_published=True)
    page_url = species_page_url(guide)
    context = {
        "guide": guide,
        "page_url": page_url,
        # Printed under the code for people without a scanner: the scheme is just noise there.
        "page_address": page_url.split("://", 1)[-1],
        "stickers": range(STICKERS_PER_SHEET),
    }
    return render(request, "education/species_stickers.html", context)
