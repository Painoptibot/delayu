from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0031_userprofile_uzhv_push_subscription"),
    ]

    operations = [
        migrations.CreateModel(
            name="GlossaryTerm",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("term", models.CharField(max_length=128, unique=True, verbose_name="Термин")),
                ("definition", models.TextField(verbose_name="Определение")),
                ("locale", models.CharField(default="ru", max_length=8, verbose_name="Язык")),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
            ],
            options={
                "verbose_name": "Термин глоссария",
                "verbose_name_plural": "Глоссарий",
                "ordering": ["sort_order", "term"],
            },
        ),
        migrations.CreateModel(
            name="PlatformReleaseVersion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("version", models.CharField(max_length=32, verbose_name="Версия")),
                ("released_at", models.DateField(verbose_name="Дата релиза")),
                ("title", models.CharField(max_length=255, verbose_name="Заголовок")),
                ("changelog", models.TextField(blank=True, verbose_name="Изменения")),
                ("is_current", models.BooleanField(default=False, verbose_name="Текущая")),
            ],
            options={
                "verbose_name": "Релиз платформы",
                "verbose_name_plural": "Релизы платформы",
                "ordering": ["-released_at", "-version"],
            },
        ),
        migrations.CreateModel(
            name="ModuleComplianceEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("screen_paths", models.JSONField(blank=True, default=list, verbose_name="Экраны (URL)")),
                ("api_paths", models.JSONField(blank=True, default=list, verbose_name="API")),
                ("role_notes", models.CharField(blank=True, max_length=500, verbose_name="Роли")),
                ("report_refs", models.CharField(blank=True, max_length=500, verbose_name="Отчёты")),
                ("evidence_notes", models.TextField(blank=True, verbose_name="Доказательства для экспертизы")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "module",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="compliance_entry",
                        to="delayu.modulecatalog",
                        verbose_name="Модуль",
                    ),
                ),
            ],
            options={
                "verbose_name": "Соответствие модуля реестру",
                "verbose_name_plural": "Журнал соответствия реестру",
            },
        ),
    ]
