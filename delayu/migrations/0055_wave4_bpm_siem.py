from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


def backfill_task_assigned_at(apps, schema_editor):
    BPMTask = apps.get_model("delayu", "BPMTask")
    for task in BPMTask.objects.select_related("instance").iterator():
        if task.assigned_at:
            continue
        task.assigned_at = task.instance.started_at or timezone.now()
        task.save(update_fields=["assigned_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0054_role_parent"),
    ]

    operations = [
        migrations.AddField(
            model_name="bpmtask",
            name="assigned_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Назначена"),
        ),
        migrations.AddField(
            model_name="bpmtask",
            name="is_escalated",
            field=models.BooleanField(default=False, verbose_name="Эскалирована"),
        ),
        migrations.AddField(
            model_name="bpmtask",
            name="escalated_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Эскалация"),
        ),
        migrations.RunPython(backfill_task_assigned_at, migrations.RunPython.noop),
        migrations.CreateModel(
            name="SiemExportConfig",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("enabled", models.BooleanField(default=False, verbose_name="Экспорт в SIEM")),
                (
                    "webhook_url",
                    models.URLField(blank=True, max_length=500, verbose_name="Webhook SIEM"),
                ),
                (
                    "last_pushed_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="Последняя отправка"),
                ),
                ("last_error", models.TextField(blank=True, verbose_name="Последняя ошибка")),
                (
                    "subsystem",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="siem_export",
                        to="delayu.subsystem",
                    ),
                ),
            ],
            options={
                "verbose_name": "Экспорт аудита в SIEM",
            },
        ),
    ]
