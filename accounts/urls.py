from django.urls import path

from . import api, views

app_name = "accounts"

urlpatterns = [
    path("logowanie", views.login_view, name="login"),
    path("rejestracja", views.register_view, name="register"),
    path("wyloguj", views.logout_view, name="logout"),
]

api_urlpatterns = [
    path("register", api.register, name="api-register"),
    path("login", api.login_api, name="api-login"),
    path("logout", api.logout_api, name="api-logout"),
]
