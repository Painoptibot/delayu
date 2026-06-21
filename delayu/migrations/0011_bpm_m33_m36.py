# M33–M36 BPM, SLA, regulations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0010_correspondence_m24_m32"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="bpmtemplate",
            name="description",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="bpmtemplate",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="slarule",
            name="code",
            field=models.SlugField(default="default", max_length=64),
        ),
        migrations.AddField(
            model_name="slarule",
            name="name",
            field=models.CharField(default="Стандартный SLA", max_length=255),
        ),
        migrations.AddField(
            model_name="slarule",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="slarule",
            name="escalate_to",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="sla_escalations",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Эскалация к",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="slarule",
            unique_together=set(),
        ),
        migrations.AlterUniqueTogether(
            name="slarule",
            unique_together={("subsystem", "code")},
        ),
        migrations.CreateModel(
            name="CaseRegulation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(max_length=64)),
                ("name", models.CharField(max_length=255)),
                ("default_working_days", models.PositiveIntegerField(default=30)),
                (
                    "applies_on_status",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("new", "Новое"),
                            ("in_progress", "В работе"),
                            ("waiting", "Ожидание"),
                            ("done", "Исполнено"),
                            ("archived", "В архиве"),
                        ],
                        max_length=20,
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "subsystem",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="case_regulations",
                        to="delayu.subsystem",
                    ),
                ),
            ],
            options={"verbose_name": "Регламент сроков", "unique_together": {("subsystem", "code")}},
        ),
    ]
