from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("players", "0014_copy_players"),
    ]

    operations = [
        migrations.AddField(
            model_name="player",
            name="emails_muted",
            field=models.BooleanField(default=False),
        ),
    ]
