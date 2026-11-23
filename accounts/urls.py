from django.urls import path

from . import api, views

app_name = "accounts"

urlpatterns = [
    path("logowanie", views.login_view, name="login"),
    path("rejestracja", views.register_view, name="register"),
    path("wyloguj", views.logout_view, name="logout"),
    path("nie-pamietam-hasla", views.password_reset_view, name="password-reset"),
    path("nie-pamietam-hasla/wyslano", views.password_reset_sent_view, name="password-reset-sent"),
    path(
        "ustaw-haslo/<str:uidb64>/<str:token>",
        views.SetNewPasswordView.as_view(),
        name="password-reset-confirm",
    ),
]

api_urlpatterns = [
    path("register", api.register, name="api-register"),
    path("login", api.login_api, name="api-login"),
    path("logout", api.logout_api, name="api-logout"),
    path("password-reset", api.password_reset, name="api-password-reset"),
    path(
        "password-reset/confirm",
        api.password_reset_confirm,
        name="api-password-reset-confirm",
    ),
]
