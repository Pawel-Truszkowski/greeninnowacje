from django.contrib import admin

from .models import Assignment, Locality, Tree, TreeSpecies, Watering


@admin.register(Locality)
class LocalityAdmin(admin.ModelAdmin):
    list_display = ["name", "lat", "lng", "created_at"]
    search_fields = ["name"]


@admin.register(TreeSpecies)
class TreeSpeciesAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name"]


@admin.register(Tree)
class TreeAdmin(admin.ModelAdmin):
    list_display = ["species", "locality", "status", "lifecycle", "planted_on", "created_at"]
    list_filter = ["status", "lifecycle", "locality"]
    search_fields = ["species", "planted_by", "notes"]
    readonly_fields = ["id", "created_at", "created_by"]
    list_select_related = ["locality"]


@admin.register(Watering)
class WateringAdmin(admin.ModelAdmin):
    """Read-only — waterings are append-only."""

    list_display = ["watered_at", "tree", "user"]
    list_select_related = ["tree__locality", "user"]
    date_hierarchy = "watered_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ["tree", "user", "started_at", "ended_at"]
    list_filter = [("ended_at", admin.EmptyFieldListFilter)]
    list_select_related = ["tree__locality", "user"]
    raw_id_fields = ["tree", "user"]
