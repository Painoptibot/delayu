from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0029_uzhv_interagency_protocols"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="telegram_chat_id",
            field=models.CharField(
                blank=True,
                help_text="Числовой chat_id для Telegram Bot API (приоритетнее @username)",
                max_length=32,
                verbose_name="Telegram chat_id",
            ),
        ),
    ]
