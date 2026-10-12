"""La temporada empieza el 1 de agosto: los partidos de agosto pasan a la temporada que empieza ese año."""
from django.db import migrations


def august_to_new_season(apps, schema_editor):
    """Partidos con fecha en agosto: de la temporada «Y-1/Y» a la «Y/Y+1»."""
    Match = apps.get_model("match", "Match")
    for match in Match.objects.filter(start_date__month=8):
        season = f"{match.start_date.year}-{match.start_date.year + 1}"
        if match.season != season:
            Match.objects.filter(pk=match.pk).update(season=season)


def august_to_old_season(apps, schema_editor):
    """Deshace el cambio: los partidos de agosto vuelven a la temporada que termina ese año."""
    Match = apps.get_model("match", "Match")
    for match in Match.objects.filter(start_date__month=8):
        season = f"{match.start_date.year - 1}-{match.start_date.year}"
        if match.season != season:
            Match.objects.filter(pk=match.pk).update(season=season)


class Migration(migrations.Migration):

    dependencies = [
        ("match", "0008_match_reopened"),
    ]

    operations = [
        migrations.RunPython(august_to_new_season, august_to_old_season),
    ]
