"""Public tree endpoints (spec §4) — no login, no personal data."""

import math
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import (
    APIException,
    PermissionDenied,
    Throttled,
    ValidationError,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.status import (
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_409_CONFLICT,
)

from accounts.permissions import IsVolunteer
from core.ratelimit import rate_limit

from .forms import TreeRegistrationForm
from .geo import is_in_poland
from .images import InvalidImage
from .models import Tree, TreePhoto
from .nominatim import reverse_locality
from .qr import qr_png, tree_card_url
from .selectors import extended_tree_card, map_tree_payload, map_trees, public_tree_card
from .services import (
    CaretakerConflict,
    DuplicateTree,
    LocalityUnknown,
    PhotoNotAllowed,
    add_photo,
    assign_caretaker,
    can_manage_photos,
    delete_photo,
    my_trees,
    record_watering,
    register_tree,
    release_caretaker,
)


class Conflict(APIException):
    """409 — the request clashes with current state (spec §4: assign to a taken tree)."""

    status_code = HTTP_409_CONFLICT
    default_detail = "Konflikt ze stanem drzewa."


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
        user=request.user if request.user.is_authenticated else None,
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


@api_view(["GET"])
@permission_classes([IsVolunteer])
def tree_extended_card(request, tree_id):
    """Card for logged-in users: adds watering authors and the caretaker's name."""
    tree = get_object_or_404(Tree.objects.select_related("locality"), pk=tree_id)
    return Response(extended_tree_card(tree))


@api_view(["POST"])
@permission_classes([IsVolunteer])
@rate_limit("watering", lambda: settings.WATERING_RATE_LIMIT, key="user")
def tree_watering(request, tree_id):
    """Mark a tree as watered. No body: the server owns the time and the author."""
    if request.limited:
        raise Throttled(detail="Za dużo zgłoszeń podlania. Spróbuj za chwilę.")
    tree = get_object_or_404(Tree, pk=tree_id, lifecycle=Tree.Lifecycle.ACTIVE)
    watering, status = record_watering(tree, request.user)
    return Response(
        {"watered_at": watering.watered_at, "status": status},
        status=HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([IsVolunteer])
def tree_assign(request, tree_id):
    tree = get_object_or_404(Tree, pk=tree_id, lifecycle=Tree.Lifecycle.ACTIVE)
    try:
        assign_caretaker(tree, request.user)
    except CaretakerConflict as conflict:
        raise Conflict(str(conflict)) from conflict
    return Response({"caretaker": request.user.display_name}, status=HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsVolunteer])
def tree_unassign(request, tree_id):
    tree = get_object_or_404(Tree, pk=tree_id)
    if not release_caretaker(tree, request.user):
        raise ValidationError({"detail": "Nie opiekujesz się tym drzewem."})
    return Response(status=HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([IsVolunteer])
def my_trees_list(request):
    """Trees I look after, most urgent first (spec §4)."""
    return Response(
        [
            map_tree_payload(tree) | {"locality": tree.locality.name}
            for tree in my_trees(request.user)
        ]
    )


@api_view(["POST"])
@permission_classes([IsVolunteer])
def tree_create(request):
    """Register a tree (spec §4). A tree within 2 m gets 409; retry with force=true."""
    data = request.data
    form = TreeRegistrationForm(data)
    if not form.is_valid():
        return Response({"errors": form.errors.get_json_data()}, status=HTTP_400_BAD_REQUEST)

    force = str(data.get("force", "")).lower() in {"1", "true", "yes"}
    try:
        tree = register_tree(
            request.user,
            locality_name=form.cleaned_data["locality_name"],
            force=force,
            **form.registration_fields(),
        )
    except DuplicateTree as duplicate:
        return Response(
            {
                "detail": str(duplicate),
                "duplicate": {
                    "id": str(duplicate.existing.pk),
                    "species": duplicate.existing.species,
                    "planted_on": duplicate.existing.planted_on,
                    "distance_m": round(duplicate.distance_m, 1),
                    "url": reverse("trees:card", kwargs={"tree_id": duplicate.existing.pk}),
                },
            },
            status=HTTP_409_CONFLICT,
        )
    except LocalityUnknown as unknown:
        return Response(
            {"errors": {"locality_name": [{"message": str(unknown), "code": "required"}]}},
            status=HTTP_400_BAD_REQUEST,
        )

    return Response(
        {
            "id": str(tree.pk),
            "status": tree.status,
            "locality": tree.locality.name,
            "url": reverse("trees:card", kwargs={"tree_id": tree.pk}),
            "qr_url": reverse("trees-api:qr", kwargs={"tree_id": tree.pk}),
        },
        status=HTTP_201_CREATED,
    )


def _requested_point(params):
    """`lat`/`lng` from the query string, checked the same way the form checks them."""
    try:
        lat, lng = Decimal(params["lat"]), Decimal(params["lng"])
    except (KeyError, InvalidOperation) as error:
        raise ValidationError("Podaj parametry lat i lng.") from error
    if not is_in_poland(lat, lng):
        raise ValidationError("Współrzędne wyglądają na spoza Polski.")
    return lat, lng


@api_view(["GET"])
@permission_classes([IsVolunteer])
# `methods` is not optional here: the decorator defaults to POST only, and a GET endpoint
# would silently keep `request.limited` False — a limiter that never limits.
@rate_limit("geocode", lambda: settings.GEOCODE_RATE_LIMIT, key="user", methods=("GET",))
def locality_hint(request):
    """Best-effort locality name for the registration form (PoC: „wykryta automatycznie").

    A hint, never a decision: the tree's locality is still resolved at save time. So no name
    is a normal answer with status 200 — a geocoder that is down, silent or merely busy must
    not look like a failure. `wait=False` is what keeps this from holding a worker for a
    second while the OSM rate window passes.
    """
    if request.limited:
        raise Throttled(detail="Za dużo zapytań o miejscowość. Spróbuj za chwilę.")
    lat, lng = _requested_point(request.query_params)
    return Response({"locality": reverse_locality(lat, lng, wait=False)})


@api_view(["POST"])
@permission_classes([IsVolunteer])
def tree_photos(request, tree_id):
    """Upload a photo: 201 with its id and the URL that serves it."""
    tree = get_object_or_404(Tree, pk=tree_id, lifecycle=Tree.Lifecycle.ACTIVE)
    # Permission before the payload: a user who may not upload should hear 403, not 400 about
    # a missing file.
    if not can_manage_photos(tree, request.user):
        raise PermissionDenied("Zdjęcie może dodać opiekun drzewa, jego autor lub administrator.")

    upload = request.FILES.get("image")
    if upload is None:
        raise ValidationError({"image": "Dołącz plik zdjęcia."})

    try:
        photo = add_photo(tree, request.user, upload)
    except PhotoNotAllowed as problem:
        raise PermissionDenied(str(problem)) from problem
    except InvalidImage as problem:
        raise ValidationError({"image": str(problem)}) from problem

    return Response(
        {
            "id": str(photo.pk),
            "url": reverse("trees:photo", kwargs={"photo_id": photo.pk}),
            "width": photo.width,
            "height": photo.height,
        },
        status=HTTP_201_CREATED,
    )


@api_view(["DELETE"])
@permission_classes([IsVolunteer])
def tree_photo_detail(request, tree_id, photo_id):
    photo = get_object_or_404(TreePhoto, pk=photo_id, tree_id=tree_id)
    try:
        delete_photo(photo, request.user)
    except PhotoNotAllowed as problem:
        raise PermissionDenied(str(problem)) from problem
    return Response(status=HTTP_204_NO_CONTENT)
