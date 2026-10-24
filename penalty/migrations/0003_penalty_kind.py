"""Motivo con código en las advertencias y limpieza del texto automático antiguo."""
from django.db import migrations, models

# Textos que la aplicación escribía sola antes de existir el motivo: no son un detalle del capitán.
AUTO_PREFIX = "Advertencia en el partido"
AUTO_EXACT = "Advertencia"


def clear_auto_reasons(apps, schema_editor):
    """Vacía el detalle de las advertencias antiguas con el texto automático (quedan como «Otro»)."""
    Penalty = apps.get_model("penalty", "Penalty")
    for pen in Penalty.objects.filter(reason__startswith=AUTO_PREFIX) | Penalty.objects.filter(reason=AUTO_EXACT):
        pen.reason = ""
        pen.save(update_fields=["reason"])


class Migration(migrations.Migration):

    dependencies = [
        ("penalty", "0002_clearer_related_names"),
    ]

    operations = [
        migrations.AddField(
            model_name="penalty",
            name="kind",
            field=models.CharField(
                choices=[
                    ("no_show", "No se presentó"),
                    ("late", "Llegó tarde"),
                    ("late_drop", "Baja de última hora"),
                    ("conduct", "Comportamiento"),
                    ("other", "Otro"),
                ],
                default="other",
                max_length=12,
                verbose_name="Motivo",
            ),
        ),
        migrations.AlterField(
            model_name="penalty",
            name="reason",
            field=models.CharField(blank=True, max_length=100, verbose_name="Detalle"),
        ),
        migrations.RunPython(clear_auto_reasons, migrations.RunPython.noop),
    ]
