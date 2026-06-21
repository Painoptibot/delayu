# ТЗ п. 321, 316, 330 — планы проверок, реконструкция, УФССП

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0045_uzhv_personal_accounts_private_fund"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="municipalbuilding",
            name="in_reconstruction_zone",
            field=models.BooleanField(default=False, verbose_name="В зоне реконструкции"),
        ),
        migrations.AddField(
            model_name="municipalbuilding",
            name="reconstruction_program",
            field=models.CharField(
                blank=True, max_length=255, verbose_name="Программа / основание реконструкции"
            ),
        ),
        migrations.AddField(
            model_name="municipalbuilding",
            name="reconstruction_since",
            field=models.DateField(blank=True, null=True, verbose_name="В зоне с"),
        ),
        migrations.CreateModel(
            name="HousingInspectionPlan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("plan_number", models.CharField(db_index=True, max_length=64, verbose_name="№ плана")),
                ("title", models.CharField(max_length=255, verbose_name="Наименование")),
                ("period_from", models.DateField(verbose_name="Период с")),
                ("period_to", models.DateField(verbose_name="Период по")),
                ("basis", models.TextField(blank=True, verbose_name="Основание внеплановых проверок")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Черновик"),
                            ("approved", "Утверждён"),
                            ("in_progress", "Исполняется"),
                            ("completed", "Выполнен"),
                        ],
                        default="draft",
                        max_length=16,
                    ),
                ),
                ("approved_at", models.DateField(blank=True, null=True, verbose_name="Дата утверждения")),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="uzhv_inspection_plans",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "subsystem",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="housing_inspection_plans",
                        to="delayu.subsystem",
                    ),
                ),
            ],
            options={
                "verbose_name": "План проверок",
                "verbose_name_plural": "Планы внеплановых проверок",
                "ordering": ["-period_from", "-plan_number"],
                "unique_together": {("subsystem", "plan_number")},
            },
        ),
        migrations.AddField(
            model_name="housinginspection",
            name="plan",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="inspections",
                to="delayu.housinginspectionplan",
                verbose_name="План внеплановых проверок",
            ),
        ),
        migrations.CreateModel(
            name="HousingEnforcementProceeding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "proceeding_number",
                    models.CharField(
                        db_index=True, max_length=128, verbose_name="№ исполнительного производства"
                    ),
                ),
                ("debtor_name", models.CharField(max_length=255, verbose_name="Должник")),
                ("check_address", models.CharField(blank=True, max_length=500, verbose_name="Адрес проверки")),
                ("court_decision", models.TextField(blank=True, verbose_name="Решение суда")),
                (
                    "initiated_at",
                    models.DateField(default=django.utils.timezone.now, verbose_name="Дата возбуждения"),
                ),
                ("completed_at", models.DateField(blank=True, null=True, verbose_name="Дата окончания")),
                ("bailiff_office", models.CharField(blank=True, max_length=255, verbose_name="Подразделение УФССП")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("open", "Возбуждено"),
                            ("in_progress", "Исполняется"),
                            ("suspended", "Приостановлено"),
                            ("completed", "Окончено"),
                            ("returned", "Возвращено в суд"),
                        ],
                        default="open",
                        max_length=16,
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "court_case",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="enforcement_proceedings",
                        to="delayu.housingcourtcase",
                        verbose_name="Судебное дело",
                    ),
                ),
                (
                    "subsystem",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="housing_enforcement_proceedings",
                        to="delayu.subsystem",
                    ),
                ),
            ],
            options={
                "verbose_name": "Исполнительное производство",
                "verbose_name_plural": "Исполнительные производства",
                "ordering": ["-initiated_at", "-proceeding_number"],
                "unique_together": {("subsystem", "proceeding_number")},
            },
        ),
    ]
