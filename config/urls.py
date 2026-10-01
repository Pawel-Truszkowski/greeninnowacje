from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from accounts.urls import api_urlpatterns as auth_api
from panel.urls import api_urlpatterns as admin_api
from trees.urls import api_urlpatterns as trees_api
from trees.urls import me_api_urlpatterns as me_api

urlpatterns = [
    path("", include("trees.urls")),
    path("", include("accounts.urls")),
    path("api/auth/", include((auth_api, "auth-api"))),
    path("api/trees/", include((trees_api, "trees-api"))),
    path("api/me/", include((me_api, "me-api"))),
    path("api/admin/", include((admin_api, "admin-api"))),
    path("admin/", include("panel.urls")),
    path("koordynator/", include("coordinator.urls")),
    path("powiadomienia/", include("notifications.urls")),
    path(settings.DJANGO_ADMIN_URL, admin.site.urls),
]
