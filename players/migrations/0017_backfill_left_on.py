from django.db import migrations
from django.db.models import Max
from django.utils import timezone


def backfill(apps, schema_editor):
    """
    Las fichas que ya estaban dadas de baja no tienen ``left_on``: se les pone el día de la última convocatoria en la
    que se apuntaron (o, si nunca se apuntaron, el de hoy) para que dejen de empeorar con las convocatorias nuevas.
    """
    Player = apps.get_model("players", "Player")
    Call = apps.get_model("call", "Call")
    today = timezone.localdate()
    for player in Player.objects.filter(in_team=False, left_on__isnull=True).iterator():
        last = Call.objects.filter(players=player).aggregate(day=Max("match__start_date"))["day"]
        Player.objects.filter(pk=player.pk).update(left_on=last or today)


class Migration(migrations.Migration):

    dependencies = [
        ("players", "0016_player_past_user_left_on"),
        ("call", "0001_initial"),
        ("match", "0001_initial"),
    ]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
