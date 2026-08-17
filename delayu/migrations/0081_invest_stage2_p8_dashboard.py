from django.db import migrations, models
from delayu.migration_ops import AddFieldIfMissing, AddIndexIfMissing, CreateModelIfMissing


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0080_invest_stage2_p7_integrations"),
    ]

    operations = [
        AddFieldIfMissing(
            model_name="investautomationconfig",
            name="options",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
