from django.db import migrations, models


PIPELINE = [
    ("new_lead", "New Lead"),
    ("contacted", "Contacted"),
    ("replied", "Replied"),
    ("qualified", "Qualified"),
    ("meeting", "Meeting scheduled"),
    ("proposal", "Proposal Sent"),
    ("active", "Active Deal"),
    ("invoice", "Invoice Sent"),
    ("setup", "Equipment Setup"),
    ("won", "Won"),
]

WORK = [
    ("proposal", "Предложение"),
    ("setup", "Монтаж"),
    ("complete", "Завершено"),
]

CUSTOMER_FORWARD = {
    "inquiry": "new_lead",
    "booked": "meeting",
    "complete": "won",
}

CUSTOMER_BACK = {
    "new_lead": "inquiry",
    "contacted": "inquiry",
    "replied": "inquiry",
    "qualified": "inquiry",
    "meeting": "booked",
    "active": "proposal",
    "invoice": "proposal",
    "won": "complete",
}

OBJECT_FORWARD = {
    "inquiry": "proposal",
    "booked": "proposal",
    "new_lead": "proposal",
    "contacted": "proposal",
    "replied": "proposal",
    "qualified": "proposal",
    "meeting": "proposal",
    "active": "proposal",
    "invoice": "proposal",
    "won": "complete",
    "complete": "complete",
}


def map_stages(apps, schema_editor):
    ServiceCustomer = apps.get_model("delayu", "ServiceCustomer")
    ServiceObject = apps.get_model("delayu", "ServiceObject")
    for old, new in CUSTOMER_FORWARD.items():
        ServiceCustomer.objects.filter(stage=old).update(stage=new)
    for old, new in OBJECT_FORWARD.items():
        ServiceObject.objects.filter(stage=old).update(stage=new)


def restore_stages(apps, schema_editor):
    ServiceCustomer = apps.get_model("delayu", "ServiceCustomer")
    ServiceDeal = apps.get_model("delayu", "ServiceDeal")
    ServiceDeal.objects.all().delete()
    for old, new in CUSTOMER_BACK.items():
        ServiceCustomer.objects.filter(stage=old).update(stage=new)


def backfill_deals(apps, schema_editor):
    ServiceCustomer = apps.get_model("delayu", "ServiceCustomer")
    ServiceDeal = apps.get_model("delayu", "ServiceDeal")
    for customer in ServiceCustomer.objects.all():
        if ServiceDeal.objects.filter(customer_id=customer.pk).exists():
            continue
        ServiceDeal.objects.create(
            subsystem_id=customer.subsystem_id,
            customer_id=customer.pk,
            number=f"DL-{customer.pk:04d}",
            title=customer.display_name,
            stage=customer.stage,
            status="won" if customer.stage == "won" else "open",
            job_type="sale",
            source="",
            city=customer.city,
            state=customer.state,
            venue="",
            placement="indoor",
            timeline="",
            lost_reason="",
        )


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0104_service_usa"),
    ]

    operations = [
        migrations.RunPython(map_stages, restore_stages),
        migrations.AlterField(
            model_name="servicecustomer",
            name="stage",
            field=models.CharField(
                choices=PIPELINE,
                default="new_lead",
                max_length=16,
                verbose_name="Стадия воронки",
            ),
        ),
        migrations.AlterField(
            model_name="serviceobject",
            name="stage",
            field=models.CharField(
                choices=WORK,
                default="proposal",
                max_length=16,
                verbose_name="Этап работ",
            ),
        ),
        migrations.CreateModel(
            name="ServiceDeal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.CharField(max_length=32, verbose_name="Номер")),
                ("title", models.CharField(max_length=255, verbose_name="Сделка")),
                (
                    "stage",
                    models.CharField(
                        choices=PIPELINE,
                        default="new_lead",
                        max_length=16,
                        verbose_name="Стадия",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("open", "Open"), ("won", "Won"), ("lost", "Lost")],
                        default="open",
                        max_length=16,
                        verbose_name="Статус",
                    ),
                ),
                (
                    "job_type",
                    models.CharField(
                        choices=[
                            ("sale", "Продажа экрана"),
                            ("rental", "Аренда на событие"),
                            ("streaming", "Трансляция"),
                            ("stage", "Сцена"),
                            ("truss", "Фермы"),
                        ],
                        default="sale",
                        max_length=16,
                        verbose_name="Задача",
                    ),
                ),
                ("source", models.CharField(blank=True, max_length=128, verbose_name="Источник")),
                ("city", models.CharField(blank=True, max_length=128, verbose_name="Город")),
                ("state", models.CharField(blank=True, max_length=32, verbose_name="Провинция")),
                ("venue", models.CharField(blank=True, max_length=255, verbose_name="Площадка")),
                (
                    "placement",
                    models.CharField(
                        choices=[("indoor", "Indoor"), ("outdoor", "Outdoor"), ("mobile", "Mobile")],
                        default="indoor",
                        max_length=16,
                        verbose_name="Где экран",
                    ),
                ),
                (
                    "width_ft",
                    models.DecimalField(
                        blank=True, decimal_places=1, max_digits=6, null=True, verbose_name="Ширина, ft"
                    ),
                ),
                (
                    "height_ft",
                    models.DecimalField(
                        blank=True, decimal_places=1, max_digits=6, null=True, verbose_name="Высота, ft"
                    ),
                ),
                ("timeline", models.CharField(blank=True, max_length=255, verbose_name="Срок проекта")),
                ("event_on", models.DateField(blank=True, null=True, verbose_name="Дата события")),
                (
                    "value",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=12, null=True, verbose_name="Сумма, C$"
                    ),
                ),
                (
                    "decision_maker",
                    models.CharField(
                        choices=[("unknown", "Не выяснено"), ("yes", "Да"), ("no", "Нет")],
                        default="unknown",
                        max_length=16,
                        verbose_name="Кто принимает решение",
                    ),
                ),
                (
                    "screen_over_30",
                    models.CharField(
                        choices=[("unknown", "Не выяснено"), ("yes", "Да"), ("no", "Нет")],
                        default="unknown",
                        max_length=16,
                        verbose_name="Экран больше 30 кв. футов",
                    ),
                ),
                (
                    "guests_over_200",
                    models.CharField(
                        choices=[("unknown", "Не выяснено"), ("yes", "Да"), ("no", "Нет")],
                        default="unknown",
                        max_length=16,
                        verbose_name="Гостей больше 200",
                    ),
                ),
                (
                    "church_project",
                    models.CharField(
                        choices=[("unknown", "Не выяснено"), ("yes", "Да"), ("no", "Нет")],
                        default="unknown",
                        max_length=16,
                        verbose_name="Церковный проект",
                    ),
                ),
                ("lost_reason", models.CharField(blank=True, max_length=255, verbose_name="Причина проигрыша")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "customer",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="deals",
                        to="delayu.servicecustomer",
                    ),
                ),
                (
                    "subsystem",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="service_deals",
                        to="delayu.subsystem",
                    ),
                ),
            ],
            options={
                "verbose_name": "Сделка LED SALES",
                "verbose_name_plural": "Сделки LED SALES",
                "ordering": ["-updated_at"],
                "unique_together": {("subsystem", "number")},
            },
        ),
        migrations.RunPython(backfill_deals, migrations.RunPython.noop),
    ]
