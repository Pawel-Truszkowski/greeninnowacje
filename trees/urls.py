from django.urls import path

from . import api, views

app_name = "trees"

urlpatterns = [
    path("", views.map_view, name="map"),
    path("moje-drzewa", views.my_trees_view, name="my"),
    path("drzewo/<uuid:tree_id>", views.tree_card, name="card"),
    path("drzewo/<uuid:tree_id>/podlano", views.water_tree, name="water"),
    path("drzewo/<uuid:tree_id>/opieka", views.take_care, name="take-care"),
    path("drzewo/<uuid:tree_id>/rezygnacja", views.stop_care, name="stop-care"),
]

api_urlpatterns = [
    path("", api.tree_list, name="list"),
    path("<uuid:tree_id>", api.tree_extended_card, name="detail"),
    path("<uuid:tree_id>/public", api.tree_public_card, name="public"),
    path("<uuid:tree_id>/qr.png", api.tree_qr, name="qr"),
    path("<uuid:tree_id>/waterings", api.tree_watering, name="waterings"),
    path("<uuid:tree_id>/assign", api.tree_assign, name="assign"),
    path("<uuid:tree_id>/unassign", api.tree_unassign, name="unassign"),
]

me_api_urlpatterns = [
    path("trees", api.my_trees_list, name="trees"),
]
