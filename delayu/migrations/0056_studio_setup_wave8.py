# Generated manually for wave 8

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0055_wave4_bpm_siem"),
    ]

    operations = [
        migrations.AddField(
            model_name="subsystem",
            name="studio_setup_state",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Прогресс мастера первичной настройки Студии",
                verbose_name="Мастер настройки Студии",
            ),
        ),
    ]
