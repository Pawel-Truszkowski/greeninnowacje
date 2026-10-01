from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.notification_list, name="list"),
    path("<int:notification_id>/otworz", views.open_notification, name="open"),
    path("przeczytane", views.mark_all_read, name="mark-all-read"),
]
