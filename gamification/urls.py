from django.urls import path

from . import api, views

app_name = "gamification"

urlpatterns = [
    path("osiagniecia", views.achievements_view, name="achievements"),
]

me_api_urlpatterns = [
    path("achievements", api.my_achievements, name="achievements"),
]
