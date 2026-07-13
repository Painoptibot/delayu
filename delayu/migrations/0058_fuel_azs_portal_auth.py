# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0057_fuel_module"),
    ]

    operations = [
        migrations.AddField(
            model_name="fuelazsstation",
            name="portal_login",
            field=models.CharField(blank=True, max_length=64, verbose_name="Логин портала АЗС"),
        ),
        migrations.AddField(
            model_name="fuelazsstation",
            name="portal_pin",
            field=models.CharField(blank=True, max_length=16, verbose_name="PIN портала АЗС"),
        ),
    ]
