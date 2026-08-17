# Generated manually for InvestFgistpDocument catalog

from django.db import migrations, models
from delayu.migration_ops import AddFieldIfMissing, AddIndexIfMissing, CreateModelIfMissing
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0087_invest_fgistp"),
    ]

    operations = [
        CreateModelIfMissing(
            name="InvestFgistpDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uin", models.CharField(max_length=128, verbose_name="UIN / внешний id")),
                ("title", models.CharField(max_length=512, verbose_name="Наименование")),
                (
                    "level",
                    models.CharField(
                        choices=[
                            ("federal", "Федеральный"),
                            ("regional", "Региональный"),
                            ("municipal", "Муниципальный"),
                        ],
                        default="regional",
                        max_length=16,
                    ),
                ),
                (
                    "doc_type",
                    models.CharField(
                        choices=[
                            ("stp", "Схема ТП"),
                            ("pzz", "ПЗЗ"),
                            ("scheme", "Схема"),
                            ("other", "Прочее"),
                        ],
                        default="stp",
                        max_length=16,
                    ),
                ),
                ("address_text", models.TextField(blank=True, verbose_name="Адрес / территория")),
                ("cadastral_numbers", models.JSONField(blank=True, default=list, verbose_name="Кадастровые номера")),
                ("municipality_name", models.CharField(blank=True, max_length=255, verbose_name="МО")),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("geometry", models.JSONField(blank=True, default=dict)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "subsystem",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="invest_fgistp_documents",
                        to="delayu.subsystem",
                    ),
                ),
            ],
            options={
                "verbose_name": "Документ ФГИС ТП (каталог)",
                "verbose_name_plural": "Документы ФГИС ТП (каталог)",
                "ordering": ["title"],
            },
        ),
        AddIndexIfMissing(
            model_name="investfgistpdocument",
            index=models.Index(fields=["subsystem", "is_active"], name="delayu_inve_subsys_fgdoc_idx"),
        ),
        AddIndexIfMissing(
            model_name="investfgistpdocument",
            index=models.Index(fields=["level"], name="delayu_inve_level_fgdoc_idx"),
        ),
        migrations.AddConstraint(
            model_name="investfgistpdocument",
            constraint=models.UniqueConstraint(
                fields=("subsystem", "uin"),
                name="uniq_invest_fgistp_doc_subsystem_uin",
            ),
        ),
    ]
