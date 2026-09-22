from django.conf import settings
from django.contrib import admin
from django.urls import path

urlpatterns = [
    path(settings.DJANGO_ADMIN_URL, admin.site.urls),
]
