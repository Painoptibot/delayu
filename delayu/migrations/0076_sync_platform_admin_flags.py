from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0075_invest_automation_bitrix"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="is_platform_admin",
            field=models.BooleanField(
                default=False,
                help_text="Доступ к контуру ЮГИт / глобальным разделам платформы",
                verbose_name="Администратор платформы",
            ),
        ),
        migrations.AddField(
            model_name="role",
            name="is_subsystem_admin",
            field=models.BooleanField(
                default=False,
                help_text="Расширенные права внутри контура подсистемы",
                verbose_name="Администратор подсистемы",
            ),
        ),
    ]
