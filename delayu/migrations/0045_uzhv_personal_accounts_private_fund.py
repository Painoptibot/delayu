# ТЗ п. 314–315 — лицевые счета, частный фонд

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0044_uzhv_status_history_contract_consents"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="HousingPersonalAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("account_number", models.CharField(db_index=True, max_length=64, verbose_name="№ лицевого счёта")),
                (
                    "living_area_sqm",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=8, null=True, verbose_name="Жилая площадь, м²"
                    ),
                ),
                (
                    "total_area_sqm",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=8, null=True, verbose_name="Общая площадь, м²"
                    ),
                ),
                (
                    "utility_services",
                    models.TextField(
                        blank=True,
                        help_text="Перечень услуг (отопление, ХВС, ГВС и т.п.)",
                        verbose_name="Коммунальные услуги",
                    ),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="Открыт")),
                ("opened_at", models.DateField(default=django.utils.timezone.now, verbose_name="Дата открытия")),
                ("closed_at", models.DateField(blank=True, null=True, verbose_name="Дата закрытия")),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "premise",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="personal_account",
                        to="delayu.municipalpremise",
                        verbose_name="Помещение",
                    ),
                ),
                (
                    "subsystem",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="housing_personal_accounts",
                        to="delayu.subsystem",
                    ),
                ),
                (
                    "tenant_citizen",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="personal_accounts",
                        to="delayu.housingcitizen",
                        verbose_name="Наниматель / собственник",
                    ),
                ),
            ],
            options={
                "verbose_name": "Лицевой счёт",
                "verbose_name_plural": "Лицевые счета",
                "ordering": ["account_number"],
                "unique_together": {("subsystem", "account_number")},
            },
        ),
        migrations.CreateModel(
            name="PrivateManagedPremise",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("address", models.CharField(max_length=500, verbose_name="Адрес")),
                ("premise_number", models.CharField(blank=True, max_length=32, verbose_name="№ помещения")),
                ("cadastral_number", models.CharField(blank=True, max_length=64, verbose_name="Кадастровый номер")),
                (
                    "area_sqm",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=8, null=True, verbose_name="Площадь, м²"
                    ),
                ),
                ("rooms", models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="Комнат")),
                ("owner_name", models.CharField(max_length=255, verbose_name="Собственник")),
                ("owner_phone", models.CharField(blank=True, max_length=32, verbose_name="Телефон")),
                ("management_since", models.DateField(blank=True, null=True, verbose_name="Управление с")),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "subsystem",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="private_managed_premises",
                        to="delayu.subsystem",
                    ),
                ),
            ],
            options={
                "verbose_name": "Помещение частного фонда",
                "verbose_name_plural": "Частный фонд (непосредственное управление)",
                "ordering": ["address", "premise_number"],
            },
        ),
        migrations.CreateModel(
            name="HousingPersonalAccountMember",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("full_name", models.CharField(max_length=255, verbose_name="ФИО")),
                (
                    "relation",
                    models.CharField(
                        choices=[
                            ("head", "Наниматель / собственник"),
                            ("spouse", "Супруг(а)"),
                            ("child", "Ребёнок"),
                            ("relative", "Родственник"),
                            ("other", "Иное"),
                        ],
                        default="other",
                        max_length=16,
                    ),
                ),
                ("birth_date", models.DateField(blank=True, null=True, verbose_name="Дата рождения")),
                (
                    "registered_from",
                    models.DateField(default=django.utils.timezone.now, verbose_name="Зарегистрирован с"),
                ),
                ("registered_to", models.DateField(blank=True, null=True, verbose_name="Снят с регистрации")),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                (
                    "account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="members",
                        to="delayu.housingpersonalaccount",
                    ),
                ),
            ],
            options={
                "verbose_name": "Член семьи (ЛС)",
                "verbose_name_plural": "Состав семьи (ЛС)",
                "ordering": ["sort_order", "full_name"],
            },
        ),
        migrations.CreateModel(
            name="HousingPersonalAccountHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("description", models.TextField(verbose_name="Событие")),
                ("changed_at", models.DateTimeField(auto_now_add=True)),
                (
                    "account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="history",
                        to="delayu.housingpersonalaccount",
                    ),
                ),
                (
                    "changed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="uzhv_account_history",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "История лицевого счёта",
                "verbose_name_plural": "История лицевых счетов",
                "ordering": ["-changed_at"],
            },
        ),
    ]
