from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0020_wave_permissions_softdelete"),
    ]

    operations = [
        migrations.AddField(
            model_name="subsystem",
            name="menu_layout",
            field=models.JSONField(blank=True, default=list, verbose_name="Меню (конструктор)"),
        ),
        migrations.AddField(
            model_name="subsystem",
            name="correspondence_workflow",
            field=models.JSONField(blank=True, default=dict, verbose_name="Маршрут СЭД"),
        ),
        migrations.AddField(
            model_name="bpmtemplate",
            name="diagram",
            field=models.JSONField(blank=True, default=dict, verbose_name="Диаграмма BPM"),
        ),
    ]
