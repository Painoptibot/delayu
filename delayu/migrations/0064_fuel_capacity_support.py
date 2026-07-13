# Generated manually
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0063_fuel_operator_admin"),
    ]

    operations = [
        migrations.AddField(
            model_name="fuelazsstation",
            name="avg_refuel_minutes",
            field=models.PositiveSmallIntegerField(default=8, verbose_name="Среднее время заправки, мин"),
        ),
        migrations.AddField(
            model_name="fuelazsstation",
            name="max_apps_override",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="Лимит заявок (ручной)"),
        ),
        migrations.AddField(
            model_name="fuelazsstation",
            name="pump_count",
            field=models.PositiveSmallIntegerField(default=2, verbose_name="Рабочих колонок"),
        ),
        migrations.AddField(
            model_name="fuelazsstation",
            name="use_manual_queue",
            field=models.BooleanField(default=False, verbose_name="Очередь вручную"),
        ),
        migrations.CreateModel(
            name="FuelPortalSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("permit_quota_liters", models.PositiveSmallIntegerField(default=30, help_text="Максимум литров в одной заявке для расчёта ёмкости АЗС", verbose_name="Квота заявки, л")),
                ("auto_queue_enabled", models.BooleanField(default=True, verbose_name="Авторасчёт очереди")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("subsystem", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="fuel_portal_settings", to="delayu.subsystem")),
            ],
            options={
                "verbose_name": "Настройки портала (топливо)",
                "verbose_name_plural": "Настройки портала (топливо)",
            },
        ),
        migrations.CreateModel(
            name="FuelSupportTicket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, verbose_name="Имя")),
                ("contact", models.CharField(max_length=255, verbose_name="Контакт")),
                ("question", models.TextField(verbose_name="Вопрос")),
                ("status", models.CharField(choices=[("new", "Новое"), ("in_progress", "В работе"), ("answered", "Отвечено"), ("closed", "Закрыто")], default="new", max_length=16, verbose_name="Статус")),
                ("operator_note", models.TextField(blank=True, verbose_name="Ответ оператора")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("citizen", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="support_tickets", to="delayu.fuelcitizen")),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fuel_support_tickets", to="delayu.subsystem")),
            ],
            options={
                "verbose_name": "Обращение в ТП",
                "verbose_name_plural": "Обращения в ТП",
                "ordering": ["-created_at"],
            },
        ),
    ]
