# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0091_fuel_ufo"),
    ]

    operations = [
        migrations.AddField(
            model_name="fuelufouserreport",
            name="phone",
            field=models.CharField(blank=True, db_index=True, default="", max_length=16),
        ),
    ]
