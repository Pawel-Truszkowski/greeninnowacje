from django.urls import path

from . import views

app_name = "coordinator"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("drzewo/<uuid:tree_id>/przypisz", views.assign, name="assign"),
    path("drzewo/<uuid:tree_id>/zwolnij", views.release, name="release"),
    path("apel", views.appeal, name="appeal"),
]
