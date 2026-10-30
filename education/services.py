"""Writing species guides — the one path the admin panel takes to change them.

The panel form judges the input (images included, through `trees.images.process_upload`);
this module stores it: it links the guide to the registration catalogue, gives it a URL
and keeps `media/gatunki` free of files no guide points at any more.
"""

from django.core.files.storage import default_storage
from django.db import transaction
from django.utils.text import slugify

from trees.models import TreeSpecies

from .models import SpeciesGuide

# The species card in the knowledge base grid: every photo the same 4:5 shape.
CARD_PHOTO_SIZE = (400, 500)

# `slugify` drops what NFKD cannot reduce to ASCII, and "ł" is a letter of its own, not an
# "l" with an accent: "Dąb szypułkowy" would become "dab-szypukowy".
POLISH_LETTERS = str.maketrans({"ł": "l", "Ł": "L"})


def species_slug(name):
    """A free ASCII slug for a new guide: "Dąb szypułkowy" → "dab-szypulkowy"."""
    base = slugify(name.translate(POLISH_LETTERS)) or "gatunek"
    slug, n = base, 1
    while SpeciesGuide.objects.filter(slug=slug).exists():
        n += 1
        slug = f"{base}-{n}"
    return slug


def catalogue_species(name):
    """The catalogue entry for `name`, added if missing — the registration form offers it too."""
    name = " ".join(name.split())
    species = TreeSpecies.objects.filter(name__iexact=name).first()
    return species or TreeSpecies.objects.create(name=name)


@transaction.atomic
def save_guide(guide, species_name, *, infographic=None, photo=None):
    """Store `guide` under `species_name`; `infographic`/`photo` are `ProcessedImage`s or None.

    None keeps the current image. A replaced file is deleted once the transaction commits:
    before that the row may still roll back to pointing at it.
    """
    guide.species = catalogue_species(species_name)
    if not guide.slug:
        # Set once: the address may already be printed or shared, so renaming keeps it.
        guide.slug = species_slug(guide.species.name)

    replaced = []
    for field, image, suffix in (("infographic", infographic, ""), ("photo", photo, "-foto")):
        if image is None:
            continue
        current = getattr(guide, field)
        if current:
            replaced.append(current.name)
        image.file.name = f"{guide.slug}{suffix}.jpg"
        setattr(guide, field, image.file)
        # Measured by the processing, so <img width height> matches the stored file.
        setattr(guide, f"{field}_width", image.width)
        setattr(guide, f"{field}_height", image.height)

    guide.save()
    # A file missing from disk frees its name, and the new one is stored under it — that one
    # must not go out with the "old" file.
    in_use = {guide.infographic.name, guide.photo.name}
    stale = [name for name in replaced if name not in in_use]
    transaction.on_commit(lambda: [default_storage.delete(name) for name in stale])
    return guide


def toggle_published(guide):
    guide.is_published = not guide.is_published
    guide.save(update_fields=["is_published", "updated_at"])
    return guide
