from django.db import migrations

# Audit requirement (spec §3): watering history must never be modified or deleted.
# The trigger works independently of the ORM — it also blocks raw SQL from the app.
# TRUNCATE is deliberately not blocked (flush in dev/tests); the app never uses it.
FORWARD = """
CREATE FUNCTION waterings_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'waterings is append-only (% blocked)', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER waterings_no_update_delete
    BEFORE UPDATE OR DELETE ON waterings
    FOR EACH ROW EXECUTE FUNCTION waterings_append_only();
"""

BACKWARD = """
DROP TRIGGER IF EXISTS waterings_no_update_delete ON waterings;
DROP FUNCTION IF EXISTS waterings_append_only();
"""


class Migration(migrations.Migration):
    dependencies = [("trees", "0001_initial")]

    operations = [migrations.RunSQL(FORWARD, BACKWARD)]
