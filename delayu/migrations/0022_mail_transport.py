from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0021_studio_editors"),
    ]

    operations = [
        migrations.CreateModel(
            name="MailTransportConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_enabled", models.BooleanField(default=False, verbose_name="Почта включена")),
                ("default_from_email", models.EmailField(blank=True, max_length=254, verbose_name="Отправитель (From)")),
                ("smtp_host", models.CharField(blank=True, max_length=255, verbose_name="SMTP хост")),
                ("smtp_port", models.PositiveIntegerField(default=587, verbose_name="SMTP порт")),
                ("smtp_use_tls", models.BooleanField(default=True, verbose_name="SMTP TLS")),
                ("smtp_username", models.CharField(blank=True, max_length=255)),
                ("smtp_password", models.CharField(blank=True, max_length=255)),
                ("imap_enabled", models.BooleanField(default=False, verbose_name="Приём IMAP")),
                ("imap_host", models.CharField(blank=True, max_length=255, verbose_name="IMAP хост")),
                ("imap_port", models.PositiveIntegerField(default=993, verbose_name="IMAP порт")),
                ("imap_use_ssl", models.BooleanField(default=True, verbose_name="IMAP SSL")),
                ("imap_username", models.CharField(blank=True, max_length=255)),
                ("imap_password", models.CharField(blank=True, max_length=255)),
                ("imap_folder", models.CharField(default="INBOX", max_length=128, verbose_name="Папка IMAP")),
                ("last_inbound_sync", models.DateTimeField(blank=True, null=True, verbose_name="Последняя синхронизация")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "subsystem",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mail_transport",
                        to="delayu.subsystem",
                    ),
                ),
            ],
            options={
                "verbose_name": "Почтовый транспорт",
                "verbose_name_plural": "Почтовые транспорты",
            },
        ),
        migrations.CreateModel(
            name="MailDeliveryLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("direction", models.CharField(choices=[("out", "Исходящее"), ("in", "Входящее")], max_length=8)),
                ("recipient", models.CharField(blank=True, max_length=255)),
                ("sender", models.CharField(blank=True, max_length=255)),
                ("subject", models.CharField(blank=True, max_length=500)),
                ("event_code", models.SlugField(blank=True, max_length=64)),
                ("success", models.BooleanField(default=True)),
                ("error_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "correspondence",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="mail_logs",
                        to="delayu.correspondence",
                    ),
                ),
                (
                    "subsystem",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mail_logs",
                        to="delayu.subsystem",
                    ),
                ),
            ],
            options={
                "verbose_name": "Журнал почты",
                "ordering": ["-created_at"],
            },
        ),
    ]
