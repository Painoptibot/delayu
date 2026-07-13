# Generated manually for fuel operator admin panel
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0062_fuel_citizen_max_consent"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="fuelazsstation",
            name="archived_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Дата архивации"),
        ),
        migrations.AddField(
            model_name="fuelazsstation",
            name="is_archived",
            field=models.BooleanField(default=False, verbose_name="В архиве"),
        ),
        migrations.AddField(
            model_name="fuelazsstation",
            name="portal_blocked",
            field=models.BooleanField(default=False, verbose_name="Доступ к порталу заблокирован"),
        ),
        migrations.AddField(
            model_name="fuelblacklistentry",
            name="deactivated_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Снято с ограничения"),
        ),
        migrations.CreateModel(
            name="FuelEventLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "channel",
                    models.CharField(
                        choices=[
                            ("operator", "Оператор штаба"),
                            ("azs", "Портал АЗС"),
                            ("citizen", "Портал жителя"),
                        ],
                        db_index=True,
                        max_length=16,
                        verbose_name="Контур",
                    ),
                ),
                ("action", models.CharField(db_index=True, max_length=64, verbose_name="Действие")),
                ("summary", models.CharField(max_length=512, verbose_name="Описание")),
                ("actor_label", models.CharField(blank=True, max_length=255, verbose_name="Инициатор")),
                ("object_type", models.CharField(blank=True, max_length=64, verbose_name="Тип объекта")),
                ("object_id", models.CharField(blank=True, max_length=64, verbose_name="ID объекта")),
                ("payload", models.JSONField(blank=True, default=dict, verbose_name="Данные")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "azs",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="event_logs",
                        to="delayu.fuelazsstation",
                    ),
                ),
                (
                    "citizen",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="event_logs",
                        to="delayu.fuelcitizen",
                    ),
                ),
                (
                    "subsystem",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fuel_event_logs",
                        to="delayu.subsystem",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="fuel_event_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Событие (топливо)",
                "verbose_name_plural": "Журнал событий (топливо)",
                "ordering": ["-created_at"],
            },
        ),
    ]
