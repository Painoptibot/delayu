"""Плановый экспорт журнала аудита (cron / compliance)."""
from django.core.management.base import BaseCommand

from delayu.management.subsystem_cli import filter_subsystems
from delayu.models import Subsystem
from delayu.services.audit import save_audit_snapshot


class Command(BaseCommand):
    help = "Сохранить CSV-снимки журнала аудита в MEDIA_ROOT/audit_exports/"

    def add_arguments(self, parser):
        parser.add_argument("--subsystem", default="", help="Код подсистемы (пусто = все)")
        parser.add_argument("--mask-pii", action="store_true", help="Маскировать ПДн в снимке")
        parser.add_argument("--action", default="", help="Фильтр по действию")

    def handle(self, *args, **options):
        code = (options["subsystem"] or "").strip()
        subs = filter_subsystems(Subsystem.objects.all(), code, stdout=self.stdout, style=self.style)
        if subs is None:
            return
        if not subs:
            self.stderr.write(self.style.ERROR("В базе нет подсистем. Запустите: manage.bat seed_demo"))
            return
        for sub in subs:
            result = save_audit_snapshot(
                sub,
                action=options["action"],
                mask_pii=options["mask_pii"],
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"{sub.code}: {result['filename']} ({result['rows']} строк)"
                )
            )
