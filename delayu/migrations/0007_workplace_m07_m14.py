# Generated manually for M07–M14 workplace fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0006_documentfile_m05"),
    ]

    operations = [
        migrations.AddField(
            model_name="taskitem",
            name="start_date",
            field=models.DateField(blank=True, null=True, verbose_name="Дата начала"),
        ),
        migrations.AddField(
            model_name="taskitem",
            name="duration_days",
            field=models.PositiveSmallIntegerField(
                default=1, verbose_name="Длительность (дней)"
            ),
        ),
        migrations.AddField(
            model_name="notification",
            name="level",
            field=models.CharField(
                choices=[
                    ("info", "Информация"),
                    ("warning", "Важно"),
                    ("urgent", "Срочно"),
                ],
                default="info",
                max_length=16,
                verbose_name="Уровень",
            ),
        ),
        migrations.AddField(
            model_name="activityevent",
            name="link_path",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="activityevent",
            name="module_code",
            field=models.CharField(blank=True, max_length=8),
        ),
        migrations.AddField(
            model_name="favorite",
            name="icon_class",
            field=models.CharField(
                default="ri-link", max_length=64, verbose_name="Иконка Remix"
            ),
        ),
        migrations.AddField(
            model_name="favorite",
            name="sort_order",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="favorite",
            name="subsystem",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="user_favorites",
                to="delayu.subsystem",
            ),
        ),
        migrations.AddField(
            model_name="savedfilter",
            name="subsystem",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="saved_filters",
                to="delayu.subsystem",
            ),
        ),
        migrations.AlterModelOptions(
            name="favorite",
            options={"ordering": ["sort_order", "label"], "verbose_name": "Избранное"},
        ),
        migrations.AlterModelOptions(
            name="savedfilter",
            options={"ordering": ["module_code", "name"]},
        ),
    ]
