from django.db import migrations

INDEX = "auth_user_email_lower_uniq"


def check_no_duplicates(apps, schema_editor):
    """Falla con la lista de emails repetidos: hay que fusionar o borrar esas cuentas antes de migrar."""
    User = apps.get_model("auth", "User")
    seen, dupes = set(), set()
    for email in User.objects.exclude(email="").values_list("email", flat=True):
        key = email.lower()
        (dupes if key in seen else seen).add(key)
    if dupes:
        raise RuntimeError(
            "No se puede garantizar un email único: hay cuentas con estos emails repetidos: "
            + ", ".join(sorted(dupes)) + ". Fusiónalas o elimínalas y vuelve a ejecutar migrate."
        )


class Migration(migrations.Migration):
    """Índice único sobre el email en minúsculas (los vacíos quedan fuera), válido en SQLite y PostgreSQL."""

    dependencies = [
        ("core", "0018_alter_userpreference_monthly_scope_and_more"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(check_no_duplicates, migrations.RunPython.noop),
        migrations.RunSQL(
            sql=f"CREATE UNIQUE INDEX {INDEX} ON auth_user (LOWER(email)) WHERE email <> ''",
            reverse_sql=f"DROP INDEX {INDEX}",
        ),
    ]
