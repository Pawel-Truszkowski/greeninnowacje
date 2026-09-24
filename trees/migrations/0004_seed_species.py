from django.db import migrations

# The list the PoC offered in its registration form (poc/rejestracja-drzewa.html).
POC_SPECIES = [
    "Brzoza brodawkowata",
    "Dąb bezszypułkowy",
    "Dąb szypułkowy",
    "Grab pospolity",
    "Jarząb pospolity",
    "Klon polny",
    "Klon zwyczajny",
    "Lipa drobnolistna",
    "Lipa szerokolistna",
    "Wiśnia ptasia",
]


def ensure(TreeSpecies, name):
    """Add the species unless an equally named one is already there.

    `get_or_create(name=...)` would not do: the unique constraint ignores case, so
    "grusza polna" next to "Grusza polna" would raise IntegrityError mid-migration.
    """
    name = name.strip()
    if name and not TreeSpecies.objects.filter(name__iexact=name).exists():
        TreeSpecies.objects.create(name=name)


def seed(apps, schema_editor):
    TreeSpecies = apps.get_model("trees", "TreeSpecies")
    Tree = apps.get_model("trees", "Tree")

    for name in POC_SPECIES:
        ensure(TreeSpecies, name)

    # Databases that already hold trees (dev, production) may use species outside the
    # list above — e.g. "Grusza polna". Without this, editing such a tree would force
    # changing its species.
    for name in Tree.objects.values_list("species", flat=True).distinct():
        ensure(TreeSpecies, name)


class Migration(migrations.Migration):
    dependencies = [("trees", "0003_treespecies")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
