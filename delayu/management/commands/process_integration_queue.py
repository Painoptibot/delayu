"""Обработка исходящей очереди интеграций (webhook, демо-коннекторы)."""
from django.core.management.base import BaseCommand

from delayu.models import Subsystem
from delayu.services.integrations import process_pending_queue


class Command(BaseCommand):
    help = "Отправить pending-сообщения шлюза интеграций (cron)"

    def add_arguments(self, parser):
        parser.add_argument("--subsystem", type=str, default="", help="Код подсистемы")
        parser.add_argument("--limit", type=int, default=50, help="Сообщений за проход")
        parser.add_argument("--all", action="store_true", help="Все подсистемы")

    def handle(self, *args, **options):
        if options["all"]:
            subs = Subsystem.objects.all()
        elif options["subsystem"]:
            subs = Subsystem.objects.filter(code=options["subsystem"])
        else:
            subs = Subsystem.objects.filter(is_active=True)

        if not subs.exists():
            self.stderr.write("Подсистемы не найдены.")
            return

        total_ok = total_fail = 0
        for sub in subs:
            result = process_pending_queue(sub, limit=options["limit"])
            total_ok += result["success"]
            total_fail += result["failed"]
            self.stdout.write(
                f"{sub.code}: обработано {result['processed']}, "
                f"успех {result['success']}, ошибок {result['failed']}"
            )
        self.stdout.write(
            self.style.SUCCESS(f"Итого: успех {total_ok}, ошибок {total_fail}")
        )
