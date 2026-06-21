"""Разовая настройка бесплатных интеграций УЖВ (seed + cron + подсказки)."""
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "seed_uzhv + sync ролей + cron (уведомления, очередь, PY-07)"

    def add_arguments(self, parser):
        parser.add_argument("--subsystem", default="uzhv")
        parser.add_argument("--skip-mail", action="store_true")
        parser.add_argument("--skip-py07", action="store_true")

    def handle(self, *args, **options):
        call_command("seed_uzhv", verbosity=1)
        call_command("sync_uzhv_role_permissions", verbosity=0)
        cron_args = ["--subsystem", options["subsystem"]]
        if options["skip_mail"]:
            cron_args.append("--skip-mail")
        if not options["skip_py07"]:
            cron_args.append("--py07")
        call_command("integrations_cron", *cron_args, verbosity=1)
        call_command("process_integration_queue", verbosity=1)
        self.stdout.write(
            self.style.SUCCESS(
                "Готово. Проверьте /integrations/ и docs/integrations-status.md. "
                "Ключи: .env (DaData, Яндекс, Telegram, DELAYU_WEBHOOK_URL, IMAP)."
            )
        )
