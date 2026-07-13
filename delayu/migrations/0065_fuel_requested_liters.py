from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0064_fuel_capacity_support"),
    ]

    operations = [
        migrations.AddField(
            model_name="fuelapplication",
            name="requested_liters",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="Необязательно: желаемый объём топлива по заявке",
                null=True,
                verbose_name="Запрашиваемый объём, л",
            ),
        ),
        migrations.AddField(
            model_name="fuelredeem",
            name="citizen_reported_liters",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=6,
                null=True,
                verbose_name="Объём по данным жителя, л",
            ),
        ),
    ]
