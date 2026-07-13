from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0060_fuel_citizen_sms_esia"),
    ]

    operations = [
        migrations.CreateModel(
            name="FuelParityRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_enabled", models.BooleanField(default=True, verbose_name="Ограничение активно")),
                (
                    "mode",
                    models.CharField(
                        choices=[
                            ("calendar", "По календарю (день месяца)"),
                            ("even", "Только чётные"),
                            ("odd", "Только нечётные"),
                        ],
                        default="calendar",
                        max_length=16,
                        verbose_name="Режим",
                    ),
                ),
                (
                    "message",
                    models.TextField(
                        blank=True,
                        help_text="Пусто — сформировать автоматически по режиму и дате.",
                        verbose_name="Текст уведомления",
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "subsystem",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fuel_parity_rule",
                        to="delayu.subsystem",
                    ),
                ),
            ],
            options={
                "verbose_name": "Правило чётности госномеров",
                "verbose_name_plural": "Правила чётности госномеров",
            },
        ),
    ]
