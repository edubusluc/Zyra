"""Equipos: ``club`` obligatorio (DB-01)."""
import django.db.models.deletion
from django.db import migrations, models


def check_no_orphans(apps, schema_editor):
    """Se niega a seguir si hay filas sin club: habría que asignarlas a mano antes (copia previa en deploy.sh)."""
    problems = []
    count = apps.get_model("team", "Team").objects.filter(club__isnull=True).count()
    if count:
        problems.append(f"{count} equipos sin club")
    if problems:
        raise RuntimeError("No se puede hacer «club» obligatorio: " + "; ".join(problems)
                           + ". Asigna esas filas a un club (o bórralas) y repite el despliegue.")


class Migration(migrations.Migration):
    """Hace obligatorio el club y protege el borrado de equipos."""

    dependencies = [
        ("core", "0030_userpreference_news_email"),
        ("team", "0008_team_default_time"),
    ]

    operations = [
        migrations.RunPython(check_no_orphans, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="team", name="club",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="teams", to="core.club"),
        ),
    ]
