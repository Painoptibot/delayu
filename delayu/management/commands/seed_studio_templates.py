"""Создать шаблоны уведомлений Студии для существующих подсистем."""
from django.core.management.base import BaseCommand

from delayu.models import Subsystem
from delayu.services.studio_notification_templates import ensure_studio_notification_templates


class Command(BaseCommand):
    help = "Создать шаблоны studio_scheduled_publish и studio.config_published (M78) для подсистем"

    def add_arguments(self, parser):
        parser.add_argument(
            "--subsystem",
            type=str,
            default="",
            help="Код подсистемы (если не указан — все активные)",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Включая неактивные подсистемы",
        )

    def handle(self, *args, **options):
        code = (options.get("subsystem") or "").strip()
        if code:
            qs = Subsystem.objects.filter(code=code)
            if not qs.exists():
                self.stderr.write(self.style.ERROR(f"Подсистема «{code}» не найдена."))
                return
        else:
            qs = Subsystem.objects.all()
            if not options["all"]:
                qs = qs.filter(status=Subsystem.Status.ACTIVE)

        total_created = 0
        for sub in qs.order_by("code"):
            created = ensure_studio_notification_templates(sub)
            total_created += created
            self.stdout.write(f"{sub.code}: +{created} шаблон(ов)")

        self.stdout.write(
            self.style.SUCCESS(f"Готово: создано {total_created} шаблонов для {qs.count()} подсистем")
        )
