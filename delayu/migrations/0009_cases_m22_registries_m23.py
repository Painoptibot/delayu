# M22–M23 registry type metadata

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0008_analytics_m15_m21"),
    ]

    operations = [
        migrations.AddField(
            model_name="registrytype",
            name="description",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="registrytype",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="registrytype",
            name="sort_order",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AlterModelOptions(
            name="registrytype",
            options={
                "ordering": ["sort_order", "name"],
                "verbose_name": "Тип реестра",
            },
        ),
    ]
