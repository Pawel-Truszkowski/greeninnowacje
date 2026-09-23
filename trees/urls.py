from django.urls import path

from . import api, views

app_name = "trees"

urlpatterns = [
    path("", views.map_view, name="map"),
    path("drzewo/<uuid:tree_id>", views.tree_card, name="card"),
]

api_urlpatterns = [
    path("", api.tree_list, name="list"),
    path("<uuid:tree_id>/public", api.tree_public_card, name="public"),
    path("<uuid:tree_id>/qr.png", api.tree_qr, name="qr"),
]
