"""La temporada empieza el 1 de agosto: el histórico SNP de agosto pasa a la temporada que empieza ese año."""
from django.db import migrations


def august_to_new_season(apps, schema_editor):
    """Puntos SNP con fecha en agosto: de la temporada «Y-1/Y» a la «Y/Y+1»."""
    History = apps.get_model("players", "SnpScoreHistory")
    for row in History.objects.filter(date__month=8):
        season = f"{row.date.year}-{row.date.year + 1}"
        if row.season != season:
            History.objects.filter(pk=row.pk).update(season=season)


class Migration(migrations.Migration):

    dependencies = [
        ("players", "0009_snp_service_queue"),
    ]

    operations = [
        migrations.RunPython(august_to_new_season, migrations.RunPython.noop),
    ]
