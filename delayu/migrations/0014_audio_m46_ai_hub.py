# M46 audio archive + M61/M66 AI

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0013_integrations_m42_m45"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="audioarchiveitem",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="audio_uploaded",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="audioarchiveitem",
            name="recorded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="audioarchiveitem",
            name="retention_until",
            field=models.DateField(blank=True, null=True, verbose_name="Хранить до"),
        ),
        migrations.AddField(
            model_name="audioarchiveitem",
            name="source_type",
            field=models.CharField(
                choices=[("call", "Звонок"), ("meeting", "Совещание"), ("other", "Прочее")],
                default="call",
                max_length=16,
            ),
        ),
        migrations.AlterModelOptions(
            name="audioarchiveitem",
            options={"ordering": ["-recorded_at", "-created_at"], "verbose_name": "Аудиозапись"},
        ),
        migrations.AddField(
            model_name="knowledgearticle",
            name="is_published",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="knowledgearticle",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterModelOptions(
            name="knowledgearticle",
            options={"ordering": ["title"], "verbose_name": "Статья базы знаний"},
        ),
        migrations.CreateModel(
            name="AiPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("model_name", models.CharField(default="demo-local", max_length=64)),
                ("max_requests_per_day", models.PositiveIntegerField(default=500)),
                ("allow_pii", models.BooleanField(default=False, verbose_name="Разрешить ПДн в промптах")),
                ("notes", models.TextField(blank=True)),
                ("subsystem", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="ai_policy", to="delayu.subsystem")),
            ],
            options={"verbose_name": "Политика ИИ"},
        ),
    ]
