# ТЗ п. 322 — предписания на проведение проверок

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0046_uzhv_inspection_plans_enforcement_reconstruction"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="housingprescription",
            options={
                "ordering": ["due_date"],
                "verbose_name": "Предписание об устранении",
                "verbose_name_plural": "Предписания об устранении",
            },
        ),
        migrations.CreateModel(
            name="HousingInspectionOrder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("order_number", models.CharField(db_index=True, max_length=64, verbose_name="№ предписания")),
                ("addressee", models.CharField(max_length=255, verbose_name="Адресат (УК, ТСЖ, ФИО)")),
                (
                    "object_type",
                    models.CharField(
                        choices=[
                            ("mkd", "МКД"),
                            ("uk", "УК"),
                            ("tsj", "ТСЖ"),
                            ("jsk", "ЖСК"),
                            ("citizen", "Гражданин"),
                        ],
                        default="mkd",
                        max_length=16,
                    ),
                ),
                ("check_address", models.CharField(blank=True, max_length=500, verbose_name="Адрес объекта")),
                ("check_subject", models.CharField(blank=True, max_length=255, verbose_name="Предмет проверки")),
                ("issued_at", models.DateField(default=django.utils.timezone.now, verbose_name="Дата выдачи")),
                ("conduct_by", models.DateField(verbose_name="Срок проведения проверки")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("issued", "Выдано"),
                            ("scheduled", "Проверка назначена"),
                            ("completed", "Проверка проведена"),
                            ("cancelled", "Отменено"),
                        ],
                        default="issued",
                        max_length=16,
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "building",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="inspection_orders",
                        to="delayu.municipalbuilding",
                    ),
                ),
                (
                    "inspection",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="conduct_order",
                        to="delayu.housinginspection",
                        verbose_name="Зарегистрированная проверка",
                    ),
                ),
                (
                    "plan",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="inspection_orders",
                        to="delayu.housinginspectionplan",
                        verbose_name="План проверок",
                    ),
                ),
                (
                    "subsystem",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="housing_inspection_orders",
                        to="delayu.subsystem",
                    ),
                ),
            ],
            options={
                "verbose_name": "Предписание на проведение проверки",
                "verbose_name_plural": "Предписания на проведение проверок",
                "ordering": ["-issued_at", "-order_number"],
                "unique_together": {("subsystem", "order_number")},
            },
        ),
    ]
