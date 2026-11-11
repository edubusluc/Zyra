from django.db import migrations, models


def mark_reopened(apps, schema_editor):
    """Los enfrentamientos que ya se reabrieron antes de este campo quedan marcados."""
    apps.get_model("match", "Match").objects.filter(reopened_at__isnull=False).update(was_closed=True)


class Migration(migrations.Migration):

    dependencies = [
        ("match", "0018_availability"),
    ]

    operations = [
        migrations.AddField(
            model_name="match",
            name="was_closed",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(mark_reopened, migrations.RunPython.noop),
    ]
