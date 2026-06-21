from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0032_registry_platform_catalog"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="totp_secret",
            field=models.CharField(blank=True, max_length=64, verbose_name="TOTP secret"),
        ),
    ]
