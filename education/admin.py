from django.contrib import admin

from .models import SpeciesGuide


@admin.register(SpeciesGuide)
class SpeciesGuideAdmin(admin.ModelAdmin):
    """For developers. Editors use the app's own panel (/admin/gatunki).

    Images are read-only here: the panel runs every upload through
    `trees.images.process_upload`, and this page would store a file exactly as sent.
    """

    list_display = ["species", "latin_name", "position", "is_published", "updated_at"]
    list_editable = ["position", "is_published"]
    list_select_related = ["species"]
    search_fields = ["species__name", "latin_name"]
    readonly_fields = [
        "infographic",
        "photo",
        "infographic_width",
        "infographic_height",
        "photo_width",
        "photo_height",
        "created_at",
        "updated_at",
    ]
