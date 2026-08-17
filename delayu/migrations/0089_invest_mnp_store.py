# Local MNP tile/feature store for Krasnodar Krai

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0088_invest_fgistp_documents"),
    ]

    operations = [
        migrations.CreateModel(
            name="InvestMnpScheme",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uin", models.CharField(db_index=True, max_length=64, unique=True, verbose_name="UIN")),
                ("name", models.CharField(blank=True, max_length=512, verbose_name="Наименование")),
                ("extent_raw", models.CharField(blank=True, max_length=255, verbose_name="Extent 3857 raw")),
                ("extent_min_x", models.FloatField(blank=True, null=True)),
                ("extent_min_y", models.FloatField(blank=True, null=True)),
                ("extent_max_x", models.FloatField(blank=True, null=True)),
                ("extent_max_y", models.FloatField(blank=True, null=True)),
                ("feature_count", models.PositiveIntegerField(default=0)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Ожидает"),
                            ("ready", "Готово"),
                            ("error", "Ошибка"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("error_text", models.TextField(blank=True)),
                ("synced_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Схема МНП (локальный store)",
                "verbose_name_plural": "Схемы МНП (локальный store)",
                "ordering": ["name", "uin"],
            },
        ),
        migrations.CreateModel(
            name="InvestMnpSyncRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("ok", models.BooleanField(default=False)),
                ("stats", models.JSONField(blank=True, default=dict)),
                ("error", models.TextField(blank=True)),
            ],
            options={
                "verbose_name": "Sync МНП store",
                "verbose_name_plural": "Sync МНП store",
                "ordering": ["-started_at"],
            },
        ),
        migrations.CreateModel(
            name="InvestMnpFeature",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("external_id", models.CharField(blank=True, db_index=True, max_length=128)),
                ("classid", models.CharField(db_index=True, max_length=32)),
                ("class_name", models.CharField(blank=True, max_length=255)),
                ("geom_type", models.CharField(blank=True, max_length=8)),
                ("properties", models.JSONField(blank=True, default=dict)),
                ("geometry", models.JSONField(blank=True, default=dict, verbose_name="Геометрия GeoJSON 4326")),
                ("bbox_min_lon", models.FloatField(db_index=True)),
                ("bbox_min_lat", models.FloatField(db_index=True)),
                ("bbox_max_lon", models.FloatField(db_index=True)),
                ("bbox_max_lat", models.FloatField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "scheme",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="features",
                        to="delayu.investmnpscheme",
                    ),
                ),
            ],
            options={
                "verbose_name": "Объект МНП (локальный store)",
                "verbose_name_plural": "Объекты МНП (локальный store)",
                "ordering": ["id"],
            },
        ),
        migrations.AddIndex(
            model_name="investmnpfeature",
            index=models.Index(
                fields=["bbox_min_lon", "bbox_max_lon", "bbox_min_lat", "bbox_max_lat"],
                name="delayu_inve_bbox_mi_7c8a1d_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="investmnpfeature",
            index=models.Index(fields=["scheme", "classid"], name="delayu_inve_scheme__mnp_cls_idx"),
        ),
    ]
