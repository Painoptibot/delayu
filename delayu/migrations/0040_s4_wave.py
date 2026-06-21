# S4 — #32, #36, #48, #50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0039_s3_wave"),
    ]

    operations = [
        migrations.AddField(
            model_name="etlrun",
            name="error_rows",
            field=models.JSONField(blank=True, default=list, help_text="Протокол ошибок по строкам (#32)"),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="onboarding_state",
            field=models.JSONField(blank=True, default=dict, help_text="Прогресс онбординга (#50): steps, dismissed_at"),
        ),
    ]
