from django.urls import path

from . import api, views

app_name = "panel"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("progi", views.thresholds, name="thresholds"),
    path("progi/przelicz", views.recompute_now, name="recompute"),
    path("uzytkownicy", views.users, name="users"),
    path("uzytkownicy/<uuid:user_id>", views.edit_user, name="edit-user"),
    path("drzewa", views.tree_list, name="trees"),
    path("drzewa/<uuid:tree_id>", views.edit_tree, name="edit-tree"),
    path("drzewa/<uuid:tree_id>/archiwizuj", views.toggle_archive, name="toggle-archive"),
]

api_urlpatterns = [
    path("stats", api.stats, name="stats"),
    path("config", api.config, name="config"),
    path("users", api.user_list, name="users"),
    path("users/<uuid:user_id>", api.user_detail, name="user-detail"),
    path("trees/<uuid:tree_id>", api.tree_detail, name="tree-detail"),
]
