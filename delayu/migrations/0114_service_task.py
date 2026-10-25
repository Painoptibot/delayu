import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0108_service_account_snapshot"),
    ]

    operations = [
        migrations.CreateModel(
            name="ServiceTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255, verbose_name="Задача")),
                ("due_on", models.DateField(blank=True, null=True, verbose_name="Срок")),
                ("done", models.BooleanField(default=False, verbose_name="Сделано")),
                ("note", models.CharField(blank=True, max_length=255, verbose_name="Заметка")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tasks", to="delayu.servicecustomer")),
                ("deal", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="tasks", to="delayu.servicedeal")),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="service_tasks", to="delayu.subsystem")),
            ],
            options={
                "verbose_name": "Задача",
                "verbose_name_plural": "Задачи",
                "ordering": ["done", "due_on", "-pk"],
            },
        ),
    ]
