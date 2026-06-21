from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0049_uzhv_household_member_ids"),
    ]

    operations = [
        migrations.AddField(
            model_name="municipalbuilding",
            name="latitude",
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                max_digits=9,
                null=True,
                verbose_name="Широта",
            ),
        ),
        migrations.AddField(
            model_name="municipalbuilding",
            name="longitude",
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                max_digits=9,
                null=True,
                verbose_name="Долгота",
            ),
        ),
    ]
