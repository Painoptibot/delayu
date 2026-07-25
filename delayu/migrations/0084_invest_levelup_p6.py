from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("delayu", "0083_invest_levelup_p5"),
    ]

    operations = [
        migrations.CreateModel(
            name="InvestProjectComment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("body", models.TextField(verbose_name="Комментарий")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "author",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="comments",
                        to="delayu.investproject",
                    ),
                ),
            ],
            options={
                "verbose_name": "Комментарий инвестпроекта",
                "verbose_name_plural": "Комментарии инвестпроектов",
                "ordering": ["created_at"],
            },
        ),
    ]
