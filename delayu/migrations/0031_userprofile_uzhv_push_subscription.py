from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0030_userprofile_telegram_chat_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="uzhv_push_subscription",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Web Push subscription (endpoint, keys) для АИС УЖВ",
                verbose_name="UZHV Web Push",
            ),
        ),
    ]
