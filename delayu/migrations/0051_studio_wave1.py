from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0050_uzhv_building_coordinates"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="subsystem",
            name="studio_draft",
            field=models.JSONField(blank=True, default=dict, verbose_name="Черновик Студии"),
        ),
        migrations.AddField(
            model_name="subsystem",
            name="studio_has_draft",
            field=models.BooleanField(default=False, verbose_name="Есть неопубликованные изменения"),
        ),
        migrations.CreateModel(
            name="RoleStudioLayout",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("dashboard", "Дашборд"),
                            ("today", "Мне на сегодня"),
                            ("cabinet", "Личный кабинет"),
                        ],
                        max_length=16,
                    ),
                ),
                ("widgets", models.JSONField(default=list)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "role",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="studio_layouts",
                        to="delayu.role",
                    ),
                ),
                (
                    "subsystem",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="role_studio_layouts",
                        to="delayu.subsystem",
                    ),
                ),
            ],
            options={
                "verbose_name": "Ролевой шаблон Студии",
                "verbose_name_plural": "Ролевые шаблоны Студии",
                "unique_together": {("role", "subsystem", "kind")},
            },
        ),
        migrations.CreateModel(
            name="StudioConfigRevision",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("version_label", models.CharField(max_length=32, verbose_name="Версия")),
                ("snapshot", models.JSONField(default=dict)),
                ("comment", models.CharField(blank=True, max_length=255, verbose_name="Комментарий")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "published_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="studio_publications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "subsystem",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="studio_revisions",
                        to="delayu.subsystem",
                    ),
                ),
            ],
            options={
                "verbose_name": "Ревизия конфигурации Студии",
                "verbose_name_plural": "Ревизии конфигурации Студии",
                "ordering": ["-created_at"],
            },
        ),
    ]
