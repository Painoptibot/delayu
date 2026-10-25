from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0105_service_led_sales"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicedeal",
            name="qualification",
            field=models.CharField(blank=True, max_length=255, verbose_name="Квалификация"),
        ),
    ]
