# Generated migration — wave 1 permissions

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0019_correspondence_mail_flags"),
    ]

    operations = [
        migrations.AddField(
            model_name="rolemodulepermission",
            name="can_view_pii",
            field=models.BooleanField(default=False, verbose_name="Просмотр ПДн"),
        ),
        migrations.AddField(
            model_name="rolemodulepermission",
            name="can_export_pii",
            field=models.BooleanField(default=False, verbose_name="Экспорт ПДн"),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="pii_consent_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Согласие на обработку ПДн"),
        ),
        migrations.AddField(
            model_name="correspondence",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Удалено"),
        ),
    ]
