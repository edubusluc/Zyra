"""La temporada empieza el 1 de agosto (los partidos de agosto cambian de temporada) y los resultados se guardan con los valores estándar."""
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


def standardize_results(apps, schema_editor):
    """Los resultados guardados con otra capitalización («Empate», «Victoria visitante») pasan al valor canónico."""
    from match import outcomes

    Match = apps.get_model("match", "Match")
    Result = apps.get_model("match", "Result")
    for model, field in ((Match, "result"), (Result, "result")):
        for row in model.objects.exclude(**{field: None}):
            current = getattr(row, field)
            if field == "result" and model is Result and current in (None, ""):
                continue
            canonical = outcomes.normalize(current)
            if canonical != current:
                model.objects.filter(pk=row.pk).update(**{field: canonical})


class Migration(migrations.Migration):

    dependencies = [
        ("match", "0008_match_reopened"),
    ]

    operations = [
        migrations.RunPython(august_to_new_season, august_to_old_season),
        migrations.RunPython(standardize_results, migrations.RunPython.noop),
    ]
