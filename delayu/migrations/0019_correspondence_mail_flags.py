from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0018_exploit_m78_m86"),
    ]

    operations = [
        migrations.AddField(
            model_name="correspondence",
            name="is_read",
            field=models.BooleanField(default=False, verbose_name="Прочитано"),
        ),
        migrations.AddField(
            model_name="correspondence",
            name="is_starred",
            field=models.BooleanField(default=False, verbose_name="В избранном"),
        ),
        migrations.AddField(
            model_name="correspondence",
            name="is_deleted",
            field=models.BooleanField(default=False, verbose_name="В корзине"),
        ),
        migrations.AddField(
            model_name="correspondence",
            name="is_draft",
            field=models.BooleanField(default=False, verbose_name="Черновик"),
        ),
        migrations.AddField(
            model_name="correspondence",
            name="is_spam",
            field=models.BooleanField(default=False, verbose_name="Спам"),
        ),
        migrations.AddField(
            model_name="correspondence",
            name="mail_label",
            field=models.CharField(
                blank=True,
                choices=[
                    ("work", "Личное"),
                    ("company", "Служебное"),
                    ("important", "Важное"),
                    ("private", "Конфиденциально"),
                ],
                max_length=20,
                verbose_name="Метка",
            ),
        ),
    ]
