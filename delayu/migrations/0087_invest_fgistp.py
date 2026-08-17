# Generated manually for InvestFgistpRecord

from django.conf import settings
from django.db import migrations, models
from delayu.migration_ops import AddFieldIfMissing, AddIndexIfMissing, CreateModelIfMissing
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("delayu", "0086_invest_extracts"),
    ]

    operations = [
        CreateModelIfMissing(
            name="InvestFgistpRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "record_type",
                    models.CharField(
                        choices=[
                            ("zones", "Зоны ТП"),
                            ("document", "Документ ТП"),
                            ("objects", "Объекты"),
                            ("other", "Прочее"),
                        ],
                        default="zones",
                        max_length=16,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Черновик"),
                            ("requested", "Запрошены"),
                            ("received", "Получены"),
                            ("verified", "Проверены"),
                            ("attached", "Приложены"),
                            ("rejected", "Отклонены"),
                            ("expired", "Просрочены"),
                        ],
                        default="draft",
                        max_length=16,
                    ),
                ),
                ("cadastral_number", models.CharField(blank=True, max_length=64, verbose_name="Кадастровый номер")),
                ("title", models.CharField(blank=True, max_length=255, verbose_name="Наименование")),
                ("document_date", models.DateField(blank=True, null=True, verbose_name="Дата документа")),
                ("valid_until", models.DateField(blank=True, null=True, verbose_name="Действует до")),
                ("file", models.FileField(blank=True, upload_to="invest/fgistp/")),
                ("payload", models.JSONField(blank=True, default=dict, verbose_name="Сведения (JSON)")),
                ("geometry", models.JSONField(blank=True, default=dict, verbose_name="Геометрия (GeoJSON)")),
                (
                    "geometry_source",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("upload", "Файл"),
                            ("import", "Импорт GeoJSON/KML"),
                            ("mock", "Mock-зоны"),
                            ("smev_derived", "Из СМЭВ"),
                        ],
                        default="",
                        max_length=16,
                    ),
                ),
                ("requested_at", models.DateTimeField(blank=True, null=True)),
                ("received_at", models.DateTimeField(blank=True, null=True)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("sla_due_at", models.DateTimeField(blank=True, null=True)),
                ("external_ids", models.JSONField(blank=True, default=dict)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "document",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="invest_fgistp_records",
                        to="delayu.documentfile",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="fgistp_records",
                        to="delayu.investproject",
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "site",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fgistp_records",
                        to="delayu.investsite",
                    ),
                ),
                (
                    "subsystem",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="invest_fgistp_records",
                        to="delayu.subsystem",
                    ),
                ),
                (
                    "verified_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Сведения ФГИС ТП",
                "verbose_name_plural": "Сведения ФГИС ТП",
                "ordering": ["-updated_at", "-id"],
            },
        ),
        AddIndexIfMissing(
            model_name="investfgistprecord",
            index=models.Index(fields=["subsystem", "status"], name="delayu_inve_subsys_fgistp_idx"),
        ),
        AddIndexIfMissing(
            model_name="investfgistprecord",
            index=models.Index(fields=["site", "status"], name="delayu_inve_site_fgistp_idx"),
        ),
    ]
