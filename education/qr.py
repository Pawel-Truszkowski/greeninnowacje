"""QR codes for species pages: stickers on saplings handed out to residents.

The URL is printed and stays in the world for years, which is why `save_guide` sets the
slug once and never follows a renamed species.
"""

from django.conf import settings
from django.urls import reverse


def species_page_url(guide):
    path = reverse("education:species", kwargs={"slug": guide.slug})
    return f"{settings.APP_BASE_URL}{path}"
