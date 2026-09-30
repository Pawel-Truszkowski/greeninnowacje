from django.urls import path

from . import api, views

app_name = "trees"

urlpatterns = [
    path("", views.map_view, name="map"),
    path("moje-drzewa", views.my_trees_view, name="my"),
    path("rejestracja-drzewa", views.register_tree_view, name="register"),
    path("drzewo/<uuid:tree_id>", views.tree_card, name="card"),
    path("drzewo/<uuid:tree_id>/podlano", views.water_tree, name="water"),
    path("drzewo/<uuid:tree_id>/opieka", views.take_care, name="take-care"),
    path("drzewo/<uuid:tree_id>/rezygnacja", views.stop_care, name="stop-care"),
    path("drzewo/<uuid:tree_id>/zdjecia", views.add_tree_photo, name="add-photo"),
    path(
        "drzewo/<uuid:tree_id>/zdjecia/<uuid:photo_id>/usun",
        views.remove_tree_photo,
        name="remove-photo",
    ),
    # The file itself. No tree in the path — the photo id is already unguessable.
    path("zdjecie/<uuid:photo_id>", views.tree_photo, name="photo"),
]

api_urlpatterns = [
    path("", api.tree_list, name="list"),
    path("nowe", api.tree_create, name="create"),
    path("locality", api.locality_hint, name="locality-hint"),
    path("<uuid:tree_id>", api.tree_extended_card, name="detail"),
    path("<uuid:tree_id>/public", api.tree_public_card, name="public"),
    path("<uuid:tree_id>/qr.png", api.tree_qr, name="qr"),
    path("<uuid:tree_id>/waterings", api.tree_watering, name="waterings"),
    path("<uuid:tree_id>/assign", api.tree_assign, name="assign"),
    path("<uuid:tree_id>/unassign", api.tree_unassign, name="unassign"),
    path("<uuid:tree_id>/photos", api.tree_photos, name="photos"),
    path("<uuid:tree_id>/photos/<uuid:photo_id>", api.tree_photo_detail, name="photo-detail"),
]

me_api_urlpatterns = [
    path("trees", api.my_trees_list, name="trees"),
]
