# M15–M21 analytics fields

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0007_workplace_m07_m14"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="reporttemplate",
            name="default_period_days",
            field=models.PositiveSmallIntegerField(
                default=30, verbose_name="Период по умолчанию (дней)"
            ),
        ),
        migrations.AddField(
            model_name="reporttemplate",
            name="description",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="reporttemplate",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="reporttemplate",
            name="report_kind",
            field=models.CharField(
                choices=[
                    ("standard", "Стандартный"),
                    ("regulatory", "Регламентированный"),
                    ("chart", "График"),
                ],
                default="standard",
                max_length=16,
                verbose_name="Тип отчёта",
            ),
        ),
        migrations.AddField(
            model_name="reportrun",
            name="period_label",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AlterModelOptions(
            name="reportrun",
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="RegulatoryReportSubmission",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("form_code", models.CharField(max_length=64)),
                ("form_name", models.CharField(max_length=255)),
                ("period_label", models.CharField(max_length=32)),
                ("period_start", models.DateField(blank=True, null=True)),
                ("period_end", models.DateField(blank=True, null=True)),
                ("version", models.PositiveSmallIntegerField(default=1)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Черновик"),
                            ("submitted", "Сдано"),
                            ("approved", "Принято"),
                        ],
                        default="draft",
                        max_length=16,
                    ),
                ),
                ("indicators", models.JSONField(blank=True, default=dict)),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "submitted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="regulatory_submissions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "subsystem",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="regulatory_reports",
                        to="delayu.subsystem",
                    ),
                ),
            ],
            options={
                "verbose_name": "Регламентированная отчётность",
                "ordering": ["-period_label", "-version"],
            },
        ),
    ]
