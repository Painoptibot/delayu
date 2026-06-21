from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0035_usersession"),
    ]

    operations = [
        migrations.AddField(
            model_name="searchindexentry",
            name="embedding",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
