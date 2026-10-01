from django.urls import path

from . import views

app_name = "coordinator"

urlpatterns = [
    path("", views.overview, name="overview"),
]
