from django.contrib import admin

from .models import UserBadge


@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    """Read-only: badges follow from what people did, nobody hands them out by hand."""

    list_display = ["user", "code", "awarded_at", "seen_at"]
    list_filter = ["code"]
    list_select_related = ["user"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
