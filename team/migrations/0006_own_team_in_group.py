"""Los equipos propios dados de baja del grupo vuelven a estar en él (nunca pueden salir)."""
from django.db import migrations


def reactivate_own_teams(apps, schema_editor):
    """Pone ``in_group`` a los equipos propios que se dieron de baja."""
    Team = apps.get_model("team", "Team")
    Team.objects.filter(is_own=True, in_group=False).update(in_group=True)


class Migration(migrations.Migration):

    dependencies = [
        ("team", "0005_photo_storage"),
    ]

    operations = [
        migrations.RunPython(reactivate_own_teams, migrations.RunPython.noop),
    ]
