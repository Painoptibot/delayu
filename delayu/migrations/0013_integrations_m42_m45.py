# M42–M45 integrations

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0012_comms_m37_m41"),
    ]

    operations = [
        migrations.AddField(
            model_name="integrationendpoint",
            name="description",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="integrationendpoint",
            name="max_retries",
            field=models.PositiveSmallIntegerField(default=3),
        ),
        migrations.AddField(
            model_name="integrationmessage",
            name="external_id",
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name="integrationmessage",
            name="processed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="integrationmessage",
            name="retry_count",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="integrationendpoint",
            name="endpoint_type",
            field=models.CharField(
                choices=[
                    ("gateway", "Шлюз"),
                    ("smev", "СМЭВ"),
                    ("rest", "REST"),
                    ("external_1c", "1С"),
                    ("external_gis", "ГИС ЖКХ"),
                    ("mail", "Почта"),
                ],
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="integrationmessage",
            name="direction",
            field=models.CharField(
                choices=[("in", "Входящее"), ("out", "Исходящее")], max_length=8
            ),
        ),
        migrations.AlterField(
            model_name="integrationmessage",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "В очереди"),
                    ("sent", "Отправлено"),
                    ("received", "Получено"),
                    ("failed", "Ошибка"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="ApiClientKey",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=128)),
                ("key_prefix", models.CharField(db_index=True, max_length=16)),
                ("key_hash", models.CharField(max_length=64)),
                ("rate_limit_per_hour", models.PositiveIntegerField(default=1000)),
                ("is_active", models.BooleanField(default=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="api_keys", to="delayu.subsystem")),
            ],
            options={"verbose_name": "API-ключ"},
        ),
    ]
