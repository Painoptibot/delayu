from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0059_fuel_analytics"),
    ]

    operations = [
        migrations.AddField(
            model_name="fuelcitizen",
            name="notify_sms",
            field=models.BooleanField(
                default=False,
                verbose_name="Дублировать пропуск по SMS",
            ),
        ),
        migrations.AddField(
            model_name="fuelcitizen",
            name="esia_oid",
            field=models.CharField(
                blank=True,
                default="",
                max_length=128,
                verbose_name="Идентификатор ЕСИА",
            ),
        ),
    ]
