import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0115_service_playbook"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicedeal",
            name="next_on",
            field=models.DateField(blank=True, null=True, verbose_name="Следующее действие"),
        ),
        migrations.AddField(
            model_name="servicedeal",
            name="revision",
            field=models.PositiveIntegerField(default=1, verbose_name="Редакция"),
        ),
        migrations.AddField(
            model_name="servicedeal",
            name="warranty_on",
            field=models.DateField(blank=True, null=True, verbose_name="Гарантия до"),
        ),
        migrations.AddField(
            model_name="servicecrewline",
            name="damaged",
            field=models.BooleanField(default=False, verbose_name="Повреждение"),
        ),
        migrations.AddField(
            model_name="serviceinvoice",
            name="kind",
            field=models.CharField(
                choices=[("deposit", "Задаток"), ("final", "Остаток")],
                default="final",
                max_length=16,
                verbose_name="Вид платежа",
            ),
        ),
        migrations.AddField(
            model_name="serviceplaybook",
            name="after_hours",
            field=models.CharField(blank=True, max_length=255, verbose_name="Текст вне часов"),
        ),
        migrations.AddField(
            model_name="serviceplaybook",
            name="approval_amount",
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=12, verbose_name="Порог согласования, C$"
            ),
        ),
        migrations.AddField(
            model_name="serviceplaybook",
            name="stale_days",
            field=models.PositiveIntegerField(default=7, verbose_name="Дней без движения"),
        ),
        migrations.AddField(
            model_name="serviceplaybook",
            name="warranty_days",
            field=models.PositiveIntegerField(default=0, verbose_name="Дней гарантии"),
        ),
        migrations.CreateModel(
            name="ServiceChecklist",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("stage", models.CharField(max_length=16, verbose_name="Стадия")),
                ("title", models.CharField(max_length=255, verbose_name="Пункт")),
                (
                    "playbook",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="checks",
                        to="delayu.serviceplaybook",
                    ),
                ),
            ],
            options={
                "verbose_name": "Пункт плейбука",
                "verbose_name_plural": "Пункты плейбука",
                "ordering": ["stage", "title"],
                "unique_together": {("playbook", "stage", "title")},
            },
        ),
        migrations.CreateModel(
            name="ServiceCheckMark",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("done", models.BooleanField(default=False, verbose_name="Сделано")),
                (
                    "deal",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="check_marks",
                        to="delayu.servicedeal",
                    ),
                ),
                (
                    "item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="marks",
                        to="delayu.servicechecklist",
                    ),
                ),
            ],
            options={"unique_together": {("deal", "item")}},
        ),
        migrations.CreateModel(
            name="ServiceNote",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("body", models.CharField(max_length=255, verbose_name="Заметка сотруднику")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "customer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="internal_notes",
                        to="delayu.servicecustomer",
                    ),
                ),
                (
                    "deal",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="internal_notes",
                        to="delayu.servicedeal",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="ServiceRoute",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("job_type", models.CharField(max_length=16, verbose_name="Вид работ")),
                ("province", models.CharField(max_length=8, verbose_name="Провинция")),
                ("owner_name", models.CharField(max_length=128, verbose_name="Владелец")),
                (
                    "subsystem",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="service_routes",
                        to="delayu.subsystem",
                    ),
                ),
            ],
            options={
                "ordering": ["province", "job_type"],
                "unique_together": {("subsystem", "job_type", "province")},
            },
        ),
        migrations.CreateModel(
            name="ServiceGear",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=128, verbose_name="Оборудование")),
                ("serial", models.CharField(max_length=64, verbose_name="Серийный номер")),
                (
                    "site",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="gears",
                        to="delayu.serviceobject",
                    ),
                ),
            ],
            options={
                "ordering": ["title"],
                "unique_together": {("site", "serial")},
            },
        ),
    ]
