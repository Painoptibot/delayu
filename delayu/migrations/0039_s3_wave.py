# S3 wave — #9, #31, #34, #37, #42

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0038_aifeedback"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ReportSchedule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("frequency", models.CharField(choices=[("daily", "Ежедневно"), ("weekly", "Еженедельно"), ("monthly", "Ежемесячно")], default="daily", max_length=16)),
                ("run_hour", models.PositiveSmallIntegerField(default=6, verbose_name="Час запуска (0–23)")),
                ("run_weekday", models.PositiveSmallIntegerField(blank=True, help_text="0=пн … 6=вс (для weekly)", null=True)),
                ("run_day", models.PositiveSmallIntegerField(blank=True, help_text="День месяца 1–28 (для monthly)", null=True)),
                ("period_days", models.PositiveSmallIntegerField(default=30)),
                ("is_active", models.BooleanField(default=True)),
                ("last_run_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="report_schedules", to="delayu.subsystem")),
                ("template", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="schedules", to="delayu.reporttemplate")),
            ],
            options={"verbose_name": "Расписание отчёта", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="DataRetentionPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("default_archive_years", models.PositiveSmallIntegerField(default=5, verbose_name="Срок хранения в архиве (лет)")),
                ("alert_days_before", models.PositiveSmallIntegerField(default=30, verbose_name="Предупреждать за (дней)")),
                ("auto_purge_enabled", models.BooleanField(default=False, verbose_name="Разрешить авто-удаление по сроку")),
                ("last_purge_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("subsystem", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="retention_policy", to="delayu.subsystem")),
            ],
            options={"verbose_name": "Политика хранения данных"},
        ),
        migrations.CreateModel(
            name="AiHumanReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("module_code", models.CharField(default="M47", max_length=8)),
                ("title", models.CharField(max_length=255)),
                ("ai_output", models.TextField()),
                ("status", models.CharField(choices=[("pending", "На проверке"), ("approved", "Утверждено"), ("rejected", "Отклонено")], default="pending", max_length=16)),
                ("review_comment", models.TextField(blank=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("reviewer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="ai_reviews_done", to=settings.AUTH_USER_MODEL)),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ai_reviews", to="delayu.subsystem")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="ai_reviews_created", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "Проверка ИИ (HITL)", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="SignatureRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("pending", "Ожидает"), ("sent", "Отправлено в КЭП"), ("signed", "Подписано"), ("failed", "Ошибка"), ("rejected", "Отклонено")], default="pending", max_length=16)),
                ("provider", models.CharField(default="mock", max_length=64)),
                ("external_id", models.CharField(blank=True, max_length=128)),
                ("error_text", models.TextField(blank=True)),
                ("meta", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(null=True, blank=True)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="signature_requests", to="delayu.documentfile")),
                ("requester", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="signature_requests", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "Запрос КЭП", "ordering": ["-created_at"]},
        ),
        migrations.AlterField(
            model_name="integrationmessage",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "В очереди"),
                    ("sent", "Отправлено"),
                    ("received", "Получено"),
                    ("failed", "Ошибка"),
                    ("dead_letter", "Dead letter"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
    ]
