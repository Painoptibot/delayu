from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0066_fuel_azs_product_stock"),
    ]

    operations = [
        migrations.AddField(
            model_name="aipolicy",
            name="ai_enabled",
            field=models.BooleanField(
                default=True,
                verbose_name="ИИ включён для подсистемы",
            ),
        ),
    ]
