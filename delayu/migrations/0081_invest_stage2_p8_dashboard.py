from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0080_invest_stage2_p7_integrations"),
    ]

    operations = [
        migrations.AddField(
            model_name="investautomationconfig",
            name="options",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
