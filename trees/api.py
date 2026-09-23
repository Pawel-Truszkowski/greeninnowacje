"""Public tree endpoints (spec §4) — no login, no personal data."""

import math

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Tree
from .qr import qr_png, tree_card_url
from .selectors import map_tree_payload, map_trees, public_tree_card

QR_CACHE_SECONDS = 86400
BBOX_FORMAT_HINT = "Oczekiwany format: bbox=west,south,east,north (lng,lat,lng,lat)."


def parse_bbox(value):
    """Parse ?bbox= into (west, south, east, north) floats, or raise ValidationError.

    The map sends Leaflet's `bounds.toBBoxString()`, i.e. "west,south,east,north"
    (lng,lat,lng,lat). Callers pass the result straight into a lat/lng range filter.
    """
    coords = value.split(",")
    if len(coords) != 4:
        raise ValidationError({"bbox": f"Podaj cztery wartości. {BBOX_FORMAT_HINT}"})

    try:
        west, south, east, north = (float(coord) for coord in coords)
    except ValueError:
        raise ValidationError(
            {"bbox": f"Współrzędne muszą być liczbami. {BBOX_FORMAT_HINT}"}
        ) from None

    # nan/inf survive float() and make every SQL comparison false, so the filter would
    # quietly return nothing instead of reporting a bad request.
    if not all(math.isfinite(coord) for coord in (west, south, east, north)):
        raise ValidationError({"bbox": f"Współrzędne muszą być skończone. {BBOX_FORMAT_HINT}"})

    if (
        not -180 <= west <= 180
        or not -180 <= east <= 180
        or not -90 <= south <= 90
        or not -90 <= north <= 90
    ):
        raise ValidationError(
            {"bbox": "Współrzędne poza zakresem (długość -180..180, szerokość -90..90)."}
        )

    # west > east is only legitimate for a view crossing the antimeridian, which trees in
    # Poland never do; rejecting it catches swapped lat/lng, the usual mistake here.
    if west > east or south > north:
        raise ValidationError({"bbox": f"Odwrócone krawędzie prostokąta. {BBOX_FORMAT_HINT}"})

    return west, south, east, north


def parse_status(value):
    if value not in Tree.Status.values:
        raise ValidationError({"status": f"Nieznany status: {value}"})
    return value


def parse_locality(value):
    if not value.isdigit():
        raise ValidationError({"locality": "Miejscowość musi być liczbą."})
    return int(value)


@api_view(["GET"])
@permission_classes([AllowAny])
def tree_list(request):
    """Trees for the map: active only, no personal data."""
    params = request.query_params
    trees = map_trees(
        status=parse_status(params["status"]) if params.get("status") else None,
        locality_id=parse_locality(params["locality"]) if params.get("locality") else None,
        bbox=parse_bbox(params["bbox"]) if params.get("bbox") else None,
    )
    return Response([map_tree_payload(tree) for tree in trees])


@api_view(["GET"])
@permission_classes([AllowAny])
def tree_public_card(request, tree_id):
    """Public card: watering history as dates only, caretaker as a yes/no flag."""
    tree = get_object_or_404(Tree.objects.select_related("locality"), pk=tree_id)
    return Response(public_tree_card(tree))


@api_view(["GET"])
@permission_classes([AllowAny])
def tree_qr(request, tree_id):
    """PNG QR code pointing at the public card; ?download=1 saves it as a file."""
    tree = get_object_or_404(Tree, pk=tree_id)
    response = HttpResponse(qr_png(tree_card_url(tree.pk)), content_type="image/png")
    response["Cache-Control"] = f"public, max-age={QR_CACHE_SECONDS}"
    if request.query_params.get("download"):
        filename = f"drzewo-{tree.pk}.png"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
