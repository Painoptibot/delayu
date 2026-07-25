from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0081_invest_stage2_p8_dashboard"),
    ]

    operations = [
        migrations.CreateModel(
            name="InvestSupportTrackItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255, verbose_name="Мера поддержки")),
                (
                    "status",
                    models.CharField(
                        choices=[("open", "Открыта"), ("in_progress", "В работе"), ("done", "Завершена")],
                        default="open",
                        max_length=16,
                    ),
                ),
                ("due_at", models.DateField(blank=True, null=True, verbose_name="Срок")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="support_track_items",
                        to="delayu.investproject",
                    ),
                ),
            ],
            options={"ordering": ["due_at", "created_at"]},
        ),
        migrations.CreateModel(
            name="InvestProtocol",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255, verbose_name="Протокол намерений")),
                ("signed_at", models.DateField(blank=True, null=True, verbose_name="Дата подписания")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "document",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="invest_protocols",
                        to="delayu.documentfile",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="protocols",
                        to="delayu.investproject",
                    ),
                ),
            ],
            options={"ordering": ["-signed_at", "-created_at"]},
        ),
        migrations.CreateModel(
            name="InvestOivApproval",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("agency_name", models.CharField(max_length=255, verbose_name="ОИВ")),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Ожидает"), ("approved", "Согласовано"), ("rejected", "Отказ")],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("due_at", models.DateField(blank=True, null=True, verbose_name="Срок")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="oiv_approvals",
                        to="delayu.investproject",
                    ),
                ),
            ],
            options={"ordering": ["due_at", "agency_name"]},
        ),
        migrations.CreateModel(
            name="InvestStopFactor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255, verbose_name="Стоп-фактор")),
                (
                    "status",
                    models.CharField(
                        choices=[("open", "Открыт"), ("blocking", "Блокирует"), ("resolved", "Снят")],
                        default="open",
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stop_factors",
                        to="delayu.investproject",
                    ),
                ),
            ],
            options={"ordering": ["status", "created_at"]},
        ),
    ]
