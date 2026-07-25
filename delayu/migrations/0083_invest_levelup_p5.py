from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0082_invest_levelup_p2"),
    ]

    operations = [
        migrations.CreateModel(
            name="InvestQuarterTarget",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("year", models.PositiveSmallIntegerField(verbose_name="Год")),
                ("quarter", models.PositiveSmallIntegerField(verbose_name="Квартал")),
                ("attraction_goal", models.PositiveIntegerField(default=0, verbose_name="План новых проектов")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "subsystem",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="invest_quarter_targets",
                        to="delayu.subsystem",
                    ),
                ),
            ],
            options={
                "ordering": ["-year", "-quarter"],
                "unique_together": {("subsystem", "year", "quarter")},
            },
        ),
    ]
