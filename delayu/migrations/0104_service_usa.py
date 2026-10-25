from django.db import migrations, models


STAGE_MAP = {
    "lead": "inquiry",
    "survey": "proposal",
    "work": "setup",
    "acceptance": "complete",
    "done": "complete",
}

STAGE_CHOICES = [
    ("inquiry", "Заявка"),
    ("proposal", "Предложение"),
    ("booked", "Бронь"),
    ("setup", "Монтаж"),
    ("complete", "Завершено"),
]


def retarget_usa(apps, schema_editor):
    ServiceCustomer = apps.get_model("delayu", "ServiceCustomer")
    ServiceObject = apps.get_model("delayu", "ServiceObject")
    ServiceChannel = apps.get_model("delayu", "ServiceChannel")
    for old, new in STAGE_MAP.items():
        ServiceCustomer.objects.filter(stage=old).update(stage=new)
        ServiceObject.objects.filter(stage=old).update(stage=new)
    ServiceChannel.objects.filter(code__in=["max", "viber", "telegram"]).delete()


def restore_stage_codes(apps, schema_editor):
    ServiceCustomer = apps.get_model("delayu", "ServiceCustomer")
    ServiceObject = apps.get_model("delayu", "ServiceObject")
    back = {
        "inquiry": "lead",
        "proposal": "survey",
        "booked": "acceptance",
        "setup": "work",
        "complete": "done",
    }
    for old, new in back.items():
        ServiceCustomer.objects.filter(stage=old).update(stage=new)
        ServiceObject.objects.filter(stage=old).update(stage=new)


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0103_service_contour"),
    ]

    operations = [
        migrations.RunPython(retarget_usa, restore_stage_codes),
        migrations.AlterField(
            model_name="servicecustomer",
            name="stage",
            field=models.CharField(
                choices=STAGE_CHOICES,
                default="inquiry",
                max_length=16,
                verbose_name="Этап",
            ),
        ),
        migrations.AddField(
            model_name="servicecustomer",
            name="city",
            field=models.CharField(blank=True, default="", max_length=128, verbose_name="Город"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="servicecustomer",
            name="state",
            field=models.CharField(blank=True, default="", max_length=32, verbose_name="Штат"),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="serviceobject",
            name="title",
            field=models.CharField(max_length=255, verbose_name="Площадка"),
        ),
        migrations.AlterField(
            model_name="serviceobject",
            name="stage",
            field=models.CharField(
                choices=STAGE_CHOICES,
                default="proposal",
                max_length=16,
                verbose_name="Этап работ",
            ),
        ),
        migrations.AddField(
            model_name="serviceobject",
            name="city",
            field=models.CharField(blank=True, default="", max_length=128, verbose_name="Город"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="serviceobject",
            name="state",
            field=models.CharField(blank=True, default="", max_length=32, verbose_name="Штат"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="serviceobject",
            name="job_type",
            field=models.CharField(
                choices=[
                    ("sale", "Продажа экрана"),
                    ("rental", "Аренда на событие"),
                    ("streaming", "Трансляция"),
                    ("stage", "Сцена"),
                    ("truss", "Фермы"),
                ],
                default="rental",
                max_length=16,
                verbose_name="Задача",
            ),
        ),
        migrations.AddField(
            model_name="serviceobject",
            name="placement",
            field=models.CharField(
                choices=[("indoor", "Indoor"), ("outdoor", "Outdoor"), ("mobile", "Mobile")],
                default="indoor",
                max_length=16,
                verbose_name="Где экран",
            ),
        ),
        migrations.AddField(
            model_name="serviceobject",
            name="width_ft",
            field=models.DecimalField(
                blank=True, decimal_places=1, max_digits=6, null=True, verbose_name="Ширина, ft"
            ),
        ),
        migrations.AddField(
            model_name="serviceobject",
            name="height_ft",
            field=models.DecimalField(
                blank=True, decimal_places=1, max_digits=6, null=True, verbose_name="Высота, ft"
            ),
        ),
        migrations.AddField(
            model_name="serviceobject",
            name="event_on",
            field=models.DateField(blank=True, null=True, verbose_name="Дата события или монтажа"),
        ),
        migrations.RenameField(
            model_name="servicevisit",
            old_name="distance_km",
            new_name="distance_mi",
        ),
        migrations.RenameField(
            model_name="servicevisit",
            old_name="rate_per_km",
            new_name="rate_per_mile",
        ),
        migrations.AlterField(
            model_name="servicevisit",
            name="distance_mi",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=8, verbose_name="Мили"),
        ),
        migrations.AlterField(
            model_name="servicevisit",
            name="rate_per_mile",
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=10, verbose_name="Ставка за милю"
            ),
        ),
    ]
