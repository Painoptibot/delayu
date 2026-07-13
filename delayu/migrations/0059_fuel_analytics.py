# Generated manually

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0058_fuel_azs_portal_auth"),
    ]

    operations = [
        migrations.AddField(
            model_name="fuelazsstation",
            name="district",
            field=models.CharField(blank=True, default="", max_length=64, verbose_name="Район"),
        ),
        migrations.CreateModel(
            name="FuelRedeemAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("plate", models.CharField(blank=True, max_length=16, verbose_name="Госномер")),
                ("success", models.BooleanField(default=False)),
                ("error_code", models.CharField(blank=True, max_length=32, verbose_name="Код ошибки")),
                ("liters", models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, verbose_name="Литры")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("azs", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="redeem_attempts", to="delayu.fuelazsstation")),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fuel_redeem_attempts", to="delayu.subsystem")),
            ],
            options={
                "verbose_name": "Попытка отпуска",
                "verbose_name_plural": "Попытки отпуска",
                "ordering": ["-created_at"],
            },
        ),
    ]
