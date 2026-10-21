from django.urls import path
from django.views.generic import TemplateView

app_name = "education"

# Static content for now; seasonal care tips from PDF 1A7 (Etap 2) will land here too.
urlpatterns = [
    path(
        "materialy-edukacyjne",
        TemplateView.as_view(template_name="education/index.html"),
        name="index",
    ),
]
