from django.contrib import admin

from .models import ActivityEvent


@admin.register(ActivityEvent)
class ActivityEventAdmin(admin.ModelAdmin):
    """Read-only: the log is evidence, edited only by `prune_activity`."""

    list_display = ["created_at", "kind", "user", "tree"]
    list_filter = ["kind"]
    date_hierarchy = "created_at"
    list_select_related = ["user", "tree"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
