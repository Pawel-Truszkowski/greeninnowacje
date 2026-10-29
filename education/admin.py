from django.contrib import admin

from .models import SpeciesGuide


@admin.register(SpeciesGuide)
class SpeciesGuideAdmin(admin.ModelAdmin):
    """Stopgap for developers: images uploaded here are stored as sent, not re-encoded.

    Editors get a page in the app's own panel (/admin), which runs uploads through
    `trees.images.process_upload`.
    """

    list_display = ["species", "latin_name", "position", "is_published", "updated_at"]
    list_editable = ["position", "is_published"]
    list_select_related = ["species"]
    search_fields = ["species__name", "latin_name"]
    readonly_fields = [
        "infographic_width",
        "infographic_height",
        "photo_width",
        "photo_height",
        "created_at",
        "updated_at",
    ]
