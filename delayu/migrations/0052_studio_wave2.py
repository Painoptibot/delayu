from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0051_studio_wave1"),
    ]

    operations = [
        migrations.AddField(
            model_name="rolemodulepermission",
            name="can_approve",
            field=models.BooleanField(default=False, verbose_name="Согласование"),
        ),
        migrations.AddField(
            model_name="rolemodulepermission",
            name="can_sign",
            field=models.BooleanField(default=False, verbose_name="Подпись"),
        ),
        migrations.AddField(
            model_name="rolemodulepermission",
            name="can_archive",
            field=models.BooleanField(default=False, verbose_name="Архивирование"),
        ),
        migrations.AddField(
            model_name="rolemodulepermission",
            name="can_bulk",
            field=models.BooleanField(default=False, verbose_name="Массовые операции"),
        ),
    ]
