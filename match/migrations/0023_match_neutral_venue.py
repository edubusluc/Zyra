"""Enfrentamientos: marca de sede neutral (Play Off de la SNP)."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("match", "0022_club_required_protect"),
    ]

    operations = [
        migrations.AddField(
            model_name="match",
            name="neutral_venue",
            field=models.BooleanField(default=False),
        ),
    ]
