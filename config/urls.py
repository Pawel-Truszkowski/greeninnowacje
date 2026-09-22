from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from accounts.urls import api_urlpatterns as auth_api
from core import views as core_views

urlpatterns = [
    path("", core_views.home, name="home"),
    path("", include("accounts.urls")),
    path("api/auth/", include((auth_api, "auth-api"))),
    path(settings.DJANGO_ADMIN_URL, admin.site.urls),
]
