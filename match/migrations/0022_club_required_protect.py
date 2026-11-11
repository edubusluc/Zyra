"""Enfrentamientos: ``club`` obligatorio y equipos protegidos contra el borrado en cascada (DB-01)."""
import django.db.models.deletion
from django.db import migrations, models


def check_no_orphans(apps, schema_editor):
    """Se niega a seguir si hay filas sin club: habría que asignarlas a mano antes (copia previa en deploy.sh)."""
    problems = []
    count = apps.get_model("match", "Match").objects.filter(club__isnull=True).count()
    if count:
        problems.append(f"{count} enfrentamientos sin club")
    if problems:
        raise RuntimeError("No se puede hacer «club» obligatorio: " + "; ".join(problems)
                           + ". Asigna esas filas a un club (o bórralas) y repite el despliegue.")


class Migration(migrations.Migration):
    """Hace obligatorio el club y protege el borrado de equipos."""

    dependencies = [
        ("core", "0030_userpreference_news_email"),
        ("team", "0009_club_required"),
        ("match", "0021_result_filled_sets"),
    ]

    operations = [
        migrations.RunPython(check_no_orphans, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="match", name="club",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="matches", to="core.club"),
        ),
        migrations.AlterField(
            model_name="match", name="local",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="local_matches", to="team.team"),
        ),
        migrations.AlterField(
            model_name="match", name="visiting",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="visiting_matches", to="team.team"),
        ),
    ]
