from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0061_fuel_parity_rule"),
    ]

    operations = [
        migrations.AddField(
            model_name="fuelcitizen",
            name="max_chat_id",
            field=models.CharField(blank=True, default="", max_length=128, verbose_name="ID чата MAX"),
        ),
        migrations.AddField(
            model_name="fuelcitizen",
            name="notify_max",
            field=models.BooleanField(default=False, verbose_name="Уведомления в MAX"),
        ),
        migrations.AddField(
            model_name="fuelcitizen",
            name="pd_consent_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Согласие на обработку ПДн"),
        ),
    ]
