from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0079_invest_stage2_p6_sites"),
    ]

    operations = [
        migrations.AddField(
            model_name="investautomationconfig",
            name="allowed_ips",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AlterField(
            model_name="investsmevrequest",
            name="status",
            field=models.CharField(
                choices=[
                    ("queued", "В очереди"),
                    ("live_pending", "Ожидает live-ответ"),
                    ("done", "Получен ответ"),
                    ("error", "Ошибка"),
                    ("applied", "Применено к карточке"),
                ],
                default="queued",
                max_length=16,
            ),
        ),
    ]
