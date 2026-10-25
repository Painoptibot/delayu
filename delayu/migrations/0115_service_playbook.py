import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0114_service_task"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicedeal",
            name="observers",
            field=models.CharField(blank=True, max_length=255, verbose_name="Наблюдатели"),
        ),
        migrations.AddField(
            model_name="servicedeal",
            name="owner_name",
            field=models.CharField(blank=True, max_length=128, verbose_name="Владелец"),
        ),
        migrations.AddField(
            model_name="servicedeal",
            name="pause_reason",
            field=models.CharField(blank=True, max_length=255, verbose_name="Причина паузы"),
        ),
        migrations.AddField(
            model_name="servicedeal",
            name="paused",
            field=models.BooleanField(default=False, verbose_name="Пауза дела"),
        ),
        migrations.AddField(
            model_name="servicemedia",
            name="deal",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="media_files",
                to="delayu.servicedeal",
            ),
        ),
        migrations.AddField(
            model_name="servicemedia",
            name="job_type",
            field=models.CharField(blank=True, max_length=16, verbose_name="Тип работ"),
        ),
        migrations.AddField(
            model_name="servicetask",
            name="kind",
            field=models.CharField(
                choices=[
                    ("call", "Звонок"),
                    ("email", "Письмо"),
                    ("visit", "Выезд"),
                    ("setup", "Монтаж"),
                    ("followup", "Дожим"),
                ],
                default="call",
                max_length=16,
                verbose_name="Шаг",
            ),
        ),
        migrations.CreateModel(
            name="ServiceJobType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=16, verbose_name="Код")),
                ("title", models.CharField(max_length=128, verbose_name="Вид работ")),
                ("active", models.BooleanField(default=True, verbose_name="В работе")),
                (
                    "subsystem",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="service_job_types",
                        to="delayu.subsystem",
                    ),
                ),
            ],
            options={
                "verbose_name": "Вид работ",
                "verbose_name_plural": "Виды работ",
                "ordering": ["title"],
                "unique_together": {("subsystem", "code")},
            },
        ),
        migrations.CreateModel(
            name="ServicePlaybook",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("job_type", models.CharField(max_length=16, verbose_name="Вид работ")),
                ("name", models.CharField(max_length=128, verbose_name="Плейбук")),
                ("sla_first_hours", models.PositiveIntegerField(default=1, verbose_name="Часы на первое касание")),
                ("sla_stage_hours", models.PositiveIntegerField(default=24, verbose_name="Часы на стадию")),
                ("mile_rate", models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name="Норма мили, C$")),
                ("hour_rate", models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name="Норма часа, C$")),
                ("crew_rate", models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name="Норма единицы силы, C$")),
                ("meeting_advances", models.BooleanField(default=True, verbose_name="Встреча двигает стадию")),
                ("gates", models.JSONField(blank=True, default=dict, verbose_name="Правила стадий")),
                ("messages", models.JSONField(blank=True, default=dict, verbose_name="Тексты стадий")),
                ("steps", models.TextField(blank=True, verbose_name="Шаги дожима")),
                (
                    "subsystem",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="service_playbooks",
                        to="delayu.subsystem",
                    ),
                ),
            ],
            options={
                "verbose_name": "Плейбук",
                "verbose_name_plural": "Плейбуки",
                "ordering": ["name"],
                "unique_together": {("subsystem", "job_type")},
            },
        ),
        migrations.CreateModel(
            name="ServiceContact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, verbose_name="Имя")),
                ("role_name", models.CharField(blank=True, max_length=128, verbose_name="Роль")),
                ("phone", models.CharField(blank=True, max_length=32, verbose_name="Телефон")),
                ("email", models.EmailField(blank=True, max_length=254, verbose_name="Почта")),
                ("decides", models.BooleanField(default=False, verbose_name="Принимает решение")),
                (
                    "customer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="contacts",
                        to="delayu.servicecustomer",
                    ),
                ),
            ],
            options={
                "verbose_name": "Контакт",
                "verbose_name_plural": "Контакты",
                "ordering": ["-decides", "name"],
            },
        ),
        migrations.CreateModel(
            name="ServiceReason",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "kind",
                    models.CharField(
                        choices=[("lost", "Проигрыш"), ("pause", "Пауза")],
                        max_length=16,
                        verbose_name="Вид",
                    ),
                ),
                ("title", models.CharField(max_length=128, verbose_name="Причина")),
                (
                    "subsystem",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="service_reasons",
                        to="delayu.subsystem",
                    ),
                ),
            ],
            options={
                "verbose_name": "Причина",
                "verbose_name_plural": "Причины",
                "ordering": ["kind", "title"],
                "unique_together": {("subsystem", "kind", "title")},
            },
        ),
        migrations.CreateModel(
            name="ServiceAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("actor", models.CharField(max_length=128, verbose_name="Кто")),
                ("action", models.CharField(max_length=64, verbose_name="Что")),
                ("detail", models.CharField(max_length=255, verbose_name="Как было")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "customer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="audits",
                        to="delayu.servicecustomer",
                    ),
                ),
                (
                    "deal",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audits",
                        to="delayu.servicedeal",
                    ),
                ),
                (
                    "subsystem",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="service_audits",
                        to="delayu.subsystem",
                    ),
                ),
            ],
            options={
                "verbose_name": "След решения",
                "verbose_name_plural": "След решений",
                "ordering": ["-created_at", "-pk"],
            },
        ),
        migrations.CreateModel(
            name="ServiceCrewLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=128, verbose_name="Сила")),
                (
                    "kind",
                    models.CharField(
                        choices=[("people", "Люди"), ("gear", "Техника")],
                        default="people",
                        max_length=16,
                        verbose_name="Вид",
                    ),
                ),
                ("planned", models.DecimalField(decimal_places=1, default=0, max_digits=8, verbose_name="План")),
                ("actual", models.DecimalField(decimal_places=1, default=0, max_digits=8, verbose_name="Факт")),
                ("unit", models.CharField(default="чел", max_length=32, verbose_name="Единица")),
                (
                    "deal",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="crew_lines",
                        to="delayu.servicedeal",
                    ),
                ),
                (
                    "site",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="crew_lines",
                        to="delayu.serviceobject",
                    ),
                ),
                (
                    "subsystem",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="service_crew_lines",
                        to="delayu.subsystem",
                    ),
                ),
            ],
            options={
                "verbose_name": "План сил",
                "verbose_name_plural": "План сил",
                "ordering": ["kind", "title"],
            },
        ),
        migrations.CreateModel(
            name="ServiceObjectDeal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "deal",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="site_links",
                        to="delayu.servicedeal",
                    ),
                ),
                (
                    "site",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deal_links",
                        to="delayu.serviceobject",
                    ),
                ),
            ],
            options={
                "verbose_name": "Площадка дела",
                "verbose_name_plural": "Площадки дел",
                "unique_together": {("site", "deal")},
            },
        ),
    ]
