from django.db import migrations

DEFAULTS = {
    "RAIN_WINDOW_DAYS": "5",
    "RAIN_THRESHOLD_MM": "10",
    "DAYS_URGENT": "5",
    "DAYS_SOON": "3",
}


def seed(apps, schema_editor):
    Config = apps.get_model("core", "Config")
    for key, value in DEFAULTS.items():
        Config.objects.get_or_create(key=key, defaults={"value": value})


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
