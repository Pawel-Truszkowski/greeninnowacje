from django.urls import path

from . import views

app_name = "education"

# Seasonal care tips from PDF 1A7 (Etap 2) will land here too.
urlpatterns = [
    path("baza-wiedzy", views.index, name="index"),
    path("baza-wiedzy/gatunki/<slug:slug>", views.species_detail, name="species"),
    path(
        "baza-wiedzy/gatunki/<slug:slug>/<str:kind>.jpg",
        views.species_image,
        name="species-image",
    ),
]
