from django.db import migrations, models


def migrate_stock_to_grades(apps, schema_editor):
    FuelAzsStation = apps.get_model("delayu", "FuelAzsStation")
    for azs in FuelAzsStation.objects.all():
        total = int(azs.stock_liters or 0)
        grade = (azs.fuel_grade or "АИ-95").upper()
        if "92" in grade:
            azs.stock_ai92_liters = total
            azs.stock_ai95_liters = 0
        else:
            azs.stock_ai95_liters = total
            azs.stock_ai92_liters = 0
        if total >= 5000:
            azs.stock_diesel_liters = max(500, total // 4)
        if azs.network and "газ" in azs.network.lower():
            azs.sells_gas = True
            azs.stock_gas_liters = max(0, total // 10)
        azs.save(
            update_fields=[
                "stock_ai92_liters",
                "stock_ai95_liters",
                "stock_diesel_liters",
                "stock_gas_liters",
                "sells_gas",
            ]
        )


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0065_fuel_requested_liters"),
    ]

    operations = [
        migrations.AddField(
            model_name="fuelazsstation",
            name="stock_ai92_liters",
            field=models.PositiveIntegerField(default=0, verbose_name="АИ-92, л"),
        ),
        migrations.AddField(
            model_name="fuelazsstation",
            name="stock_ai95_liters",
            field=models.PositiveIntegerField(default=0, verbose_name="АИ-95, л"),
        ),
        migrations.AddField(
            model_name="fuelazsstation",
            name="stock_diesel_liters",
            field=models.PositiveIntegerField(default=0, verbose_name="Дизель, л"),
        ),
        migrations.AddField(
            model_name="fuelazsstation",
            name="stock_gas_liters",
            field=models.PositiveIntegerField(default=0, verbose_name="Газ (СУГ), л"),
        ),
        migrations.AddField(
            model_name="fuelazsstation",
            name="sells_ai92",
            field=models.BooleanField(default=True, verbose_name="Продаёт АИ-92"),
        ),
        migrations.AddField(
            model_name="fuelazsstation",
            name="sells_ai95",
            field=models.BooleanField(default=True, verbose_name="Продаёт АИ-95"),
        ),
        migrations.AddField(
            model_name="fuelazsstation",
            name="sells_diesel",
            field=models.BooleanField(default=True, verbose_name="Продаёт дизель"),
        ),
        migrations.AddField(
            model_name="fuelazsstation",
            name="sells_gas",
            field=models.BooleanField(default=False, verbose_name="Продаёт газ"),
        ),
        migrations.AlterField(
            model_name="fuelazsstation",
            name="stock_liters",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Авто: АИ-92 + АИ-95, для программы пропусков",
                verbose_name="Остаток бензина (сумма), л",
            ),
        ),
        migrations.RunPython(migrate_stock_to_grades, migrations.RunPython.noop),
    ]
