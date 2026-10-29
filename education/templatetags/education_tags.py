from django import template

from education.models import SpeciesGuide

register = template.Library()


@register.simple_tag
def species_guide(species_name):
    """The published guide for a tree's species, or None.

    `Tree.species` is free text typed or picked by a volunteer, so it is only ever a lookup
    key here — it never reaches a URL; the link is built from the guide's own slug.
    """
    name = (species_name or "").strip()
    if not name:
        return None
    return (
        SpeciesGuide.objects.filter(species__name__iexact=name, is_published=True)
        .only("slug")
        .first()
    )
