from django.db import models
from django.utils import timezone

# A line holding only a dash is a field the infographic left blank; it has no text version.
BLANK_MARKS = {"", "-", "—", "–"}


def _lines(text):
    return [line.strip() for line in text.splitlines() if line.strip() not in BLANK_MARKS]


def _pairs(text):
    """Lines of `title | description` as pairs; a line without `|` has an empty description."""
    pairs = []
    for line in _lines(text):
        title, _, rest = line.partition("|")
        rest = rest.strip()
        if rest in BLANK_MARKS:
            rest = ""
        pairs.append((title.strip(), rest))
    return pairs


class SpeciesGuide(models.Model):
    """A knowledge base page about one species: its infographic and the infographic as text.

    Hangs off the registration catalogue (`TreeSpecies`), so the name is defined once and a
    tree card can link to the guide of the species it was registered with. The text fields
    hold one item per line, which keeps them editable in a plain form; the properties below
    turn them into lists. The text version is not optional decoration: text inside an image
    reaches neither screen readers nor search (WCAG 1.1.1).
    """

    species = models.OneToOneField(
        "trees.TreeSpecies",
        on_delete=models.PROTECT,
        related_name="guide",
        verbose_name="gatunek",
    )
    # The public URL; ASCII so it survives being typed, printed or shared.
    slug = models.SlugField("adres", max_length=80, unique=True)
    latin_name = models.CharField("nazwa łacińska", max_length=120)
    summary = models.TextField("opis")
    traits = models.TextField(
        "najważniejsze cechy", blank=True, help_text="Jedna cecha w linii: „Tytuł | opis”."
    )
    params = models.TextField(
        "wymagania", blank=True, help_text="Jeden parametr w linii: „Etykieta | wartość”."
    )
    plant_where = models.TextField(
        "gdzie najlepiej sadzić", blank=True, help_text="Jedno miejsce w linii."
    )
    dislikes = models.TextField("czego nie lubi", blank=True, help_text="Jedna pozycja w linii.")

    # Dimensions for <img width height>, so the page does not jump while an image loads;
    # Django fills them in whenever a file is assigned.
    infographic = models.ImageField(
        "infografika",
        upload_to="gatunki/",
        width_field="infographic_width",
        height_field="infographic_height",
    )
    infographic_width = models.PositiveIntegerField(default=0)
    infographic_height = models.PositiveIntegerField(default=0)
    photo = models.ImageField(
        "zdjęcie na kartę",
        upload_to="gatunki/",
        width_field="photo_width",
        height_field="photo_height",
    )
    photo_width = models.PositiveIntegerField(default=0)
    photo_height = models.PositiveIntegerField(default=0)

    position = models.PositiveSmallIntegerField("kolejność", default=0)
    is_published = models.BooleanField("opublikowany", default=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "species_guides"
        verbose_name = "opis gatunku"
        verbose_name_plural = "opisy gatunków"
        ordering = ["position", "slug"]

    def __str__(self):
        return self.species.name

    @property
    def name(self):
        return self.species.name

    @property
    def trait_list(self):
        return _pairs(self.traits)

    @property
    def param_list(self):
        # A trait reads fine as a bare title; a parameter without a value says nothing.
        return [(label, value) for label, value in _pairs(self.params) if value]

    @property
    def plant_where_list(self):
        return _lines(self.plant_where)

    @property
    def dislike_list(self):
        return _lines(self.dislikes)

    @property
    def version(self):
        """Cache-buster for image URLs: a replaced image gets a new URL, so no stale copy."""
        return int(self.updated_at.timestamp()) if self.updated_at else 0
