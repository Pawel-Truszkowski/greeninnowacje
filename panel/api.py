"""Admin API (spec §4). Same rules as the pages — the forms are shared."""

from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST

from accounts.models import User
from accounts.permissions import IsAppAdmin
from trees.models import Tree

from .forms import ThresholdsForm, TreeAdminForm, UserAdminForm
from .selectors import dashboard_stats


def _errors(form):
    return Response({"errors": form.errors.get_json_data()}, status=HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAppAdmin])
def stats(request):
    data = dashboard_stats()
    data["needs_attention"] = [
        {"id": str(tree.pk), "species": tree.species, "locality": tree.locality.name}
        for tree in data["needs_attention"]
    ]
    return Response(data)


@api_view(["GET", "PUT"])
@permission_classes([IsAppAdmin])
def config(request):
    if request.method == "GET":
        return Response(ThresholdsForm.initial_from_config())

    form = ThresholdsForm(request.data)
    if not form.is_valid():
        return _errors(form)
    form.save()
    return Response(ThresholdsForm.initial_from_config())


@api_view(["GET"])
@permission_classes([IsAppAdmin])
def user_list(request):
    return Response(
        [
            {
                "id": str(person.pk),
                "email": person.email,
                "display_name": person.display_name,
                "role": person.role,
                "is_active": person.is_active,
            }
            for person in User.objects.order_by("display_name")
        ]
    )


@api_view(["PATCH"])
@permission_classes([IsAppAdmin])
def user_detail(request, user_id):
    person = get_object_or_404(User, pk=user_id)
    data = {
        "role": request.data.get("role", person.role),
        "is_active": request.data.get("is_active", person.is_active),
    }
    form = UserAdminForm(data, instance=person, editor=request.user)
    if not form.is_valid():
        return _errors(form)
    form.save()
    return Response({"id": str(person.pk), "role": person.role, "is_active": person.is_active})


@api_view(["PATCH"])
@permission_classes([IsAppAdmin])
def tree_detail(request, tree_id):
    tree = get_object_or_404(Tree, pk=tree_id)
    data = {field: getattr(tree, field) for field in ["planted_by", "notes", "lifecycle"]}
    data |= {"species": tree.species, "planted_on": tree.planted_on, "locality": tree.locality_id}
    data |= {key: value for key, value in request.data.items()}

    form = TreeAdminForm(data, instance=tree)
    if not form.is_valid():
        return _errors(form)
    tree = form.save()
    return Response(
        {
            "id": str(tree.pk),
            "species": tree.species,
            "lifecycle": tree.lifecycle,
            "locality": tree.locality.name,
        }
    )
