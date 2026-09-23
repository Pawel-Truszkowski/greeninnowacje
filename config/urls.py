from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from accounts.urls import api_urlpatterns as auth_api
from trees.urls import api_urlpatterns as trees_api
from trees.urls import me_api_urlpatterns as me_api

urlpatterns = [
    path("", include("trees.urls")),
    path("", include("accounts.urls")),
    path("api/auth/", include((auth_api, "auth-api"))),
    path("api/trees/", include((trees_api, "trees-api"))),
    path("api/me/", include((me_api, "me-api"))),
    path(settings.DJANGO_ADMIN_URL, admin.site.urls),
]
