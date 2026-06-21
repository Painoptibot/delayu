# M24–M32 correspondence extensions

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0009_cases_m22_registries_m23"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="correspondence",
            name="linked_incoming",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="outgoing_replies",
                to="delayu.correspondence",
                verbose_name="Связанное входящее",
            ),
        ),
        migrations.CreateModel(
            name="PrintTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(max_length=64)),
                ("name", models.CharField(max_length=255)),
                ("body", models.TextField(help_text="Плейсхолдеры: {{reg_number}}, {{subject}}, {{counterparty}}, {{reg_date}}")),
                ("is_active", models.BooleanField(default=True)),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="print_templates", to="delayu.subsystem")),
            ],
            options={"verbose_name": "Печатная форма", "unique_together": {("subsystem", "code")}},
        ),
        migrations.CreateModel(
            name="CorrespondenceRoute",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("comment", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("correspondence", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="routes", to="delayu.correspondence")),
                ("from_user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="routes_sent", to=settings.AUTH_USER_MODEL)),
                ("to_user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="routes_received", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "Маршрут корреспонденции", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="CorrespondenceEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(choices=[("registered", "Регистрация"), ("routed", "Переадресация"), ("status", "Смена статуса"), ("linked", "Связь с делом"), ("signed", "Подпись"), ("version", "Новая версия"), ("comment", "Комментарий")], max_length=16)),
                ("description", models.CharField(max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("correspondence", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="delayu.correspondence")),
                ("document", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="correspondence_events", to="delayu.documentfile")),
            ],
            options={"verbose_name": "Событие корреспонденции", "ordering": ["-created_at"]},
        ),
    ]
