from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render

from .models import SpeciesGuide

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
    }
    return render(request, "education/species.html", context)


def species_image(request, slug, kind):
    """Public, unlike tree photos (`trees.views.tree_photo`): a guide is published content.

    The content type is fixed for the same reason as there — every stored image is a JPEG,
    and a constant plus the global `nosniff` leaves no room for content-type games. The URL
    carries `?v=<updated_at>`, so a day of caching never shows a replaced image.
    """
    field = IMAGE_KINDS.get(kind)
    if field is None:
        raise Http404
    guide = get_object_or_404(SpeciesGuide, slug=slug, is_published=True)
    response = FileResponse(getattr(guide, field).open("rb"), content_type="image/jpeg")
    response["Cache-Control"] = "public, max-age=86400"
    return response
