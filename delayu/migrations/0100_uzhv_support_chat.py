from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def add_u04(apps, schema_editor):
    ModuleCatalog = apps.get_model("delayu", "ModuleCatalog")
    ModuleCatalog.objects.update_or_create(
        code="U04",
        defaults={
            "name": "Обратная связь УЖВ",
            "description": "Чат с технической поддержкой и помощником Odysseus.",
            "group": "comms",
            "is_core": False,
            "sort_order": 104,
            "is_active": True,
        },
    )


def remove_u04(apps, schema_editor):
    ModuleCatalog = apps.get_model("delayu", "ModuleCatalog")
    ModuleCatalog.objects.filter(code="U04").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0094_invest_ai_chat_ticket"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UzhvSupportThread",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("subject", models.CharField(max_length=200, verbose_name="Тема")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("open", "Диалог с Odysseus"),
                            ("escalated", "У специалиста ТП"),
                            ("answered", "Есть ответ ТП"),
                            ("closed", "Закрыто"),
                        ],
                        db_index=True,
                        default="open",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "author",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="uzhv_support_threads",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "subsystem",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="uzhv_support_threads",
                        to="delayu.subsystem",
                    ),
                ),
            ],
            options={
                "verbose_name": "Обращение в ТП УЖВ",
                "verbose_name_plural": "Обращения в ТП УЖВ",
                "ordering": ["-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="UzhvSupportMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("user", "Пользователь"),
                            ("assistant", "Odysseus"),
                            ("specialist", "Специалист ТП"),
                            ("system", "Система"),
                        ],
                        max_length=16,
                    ),
                ),
                ("body", models.TextField()),
                ("engine", models.CharField(blank=True, max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "author",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="uzhv_support_messages",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "thread",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="messages",
                        to="delayu.uzhvsupportthread",
                    ),
                ),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.RunPython(add_u04, remove_u04),
    ]
