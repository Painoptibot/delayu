"""Синхронизация in-app уведомлений по просроченным срокам АИС УЖВ (cron / планировщик)."""
from django.core.management.base import BaseCommand

from delayu.models import Subsystem
from delayu.services.uzhv_notifications import sync_uzhv_deadline_notifications


class Command(BaseCommand):
    help = "Создать уведомления по просроченным срокам УЖВ для подсистемы (без привязки к визиту на hub)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--subsystem",
            type=str,
            default="uzhv",
            help="Код подсистемы (по умолчанию uzhv)",
        )
        parser.add_argument(
            "--all-uzhv",
            action="store_true",
            help="Обработать все подсистемы с industry_template=uzhv",
        )

    def handle(self, *args, **options):
        if options["all_uzhv"]:
            qs = Subsystem.objects.filter(industry_template="uzhv")
        else:
            qs = Subsystem.objects.filter(code=options["subsystem"])
        if not qs.exists():
            self.stderr.write("Подсистема не найдена.")
            return
        total_created = 0
        total_push = 0
        for sub in qs:
            result = sync_uzhv_deadline_notifications(sub)
            total_created += result["created"]
            total_push += result["push_sent"]
            self.stdout.write(
                f"{sub.code}: уведомлений {result['created']}, web push {result['push_sent']}"
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Итого: уведомлений {total_created}, web push {total_push}"
            )
        )
