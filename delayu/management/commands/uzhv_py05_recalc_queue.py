"""PY-05 — пересчёт очереди учётных дел."""
from django.core.management.base import BaseCommand

from delayu.management.subsystem_cli import filter_subsystems
from delayu.models import Subsystem
from delayu.services.uzhv_py_cli import EXIT_CONFIG, setup_py_logger
from delayu.services.uzhv_queue import recalculate_housing_queue


class Command(BaseCommand):
    help = "PY-05: пересчёт queue_position по категории и дате учёта"

    def add_arguments(self, parser):
        parser.add_argument("--subsystem", default="uzhv")
        parser.add_argument("--dry-run", action="store_true", help="Без записи в БД")
        parser.add_argument("--log-file", default="")

    def handle(self, *args, **options):
        logger = setup_py_logger("py05", options["log_file"] or None)
        subs = filter_subsystems(
            Subsystem.objects.all(), options["subsystem"], stdout=self.stdout, style=self.style
        )
        if subs is None or not subs:
            raise SystemExit(EXIT_CONFIG)

        result = recalculate_housing_queue(subs[0], dry_run=options["dry_run"])
        mode = "DRY-RUN" if options["dry_run"] else "APPLY"
        logger.info("[%s] Дел в очереди: %s, обновлено: %s", mode, result.total, result.updated)
        for line in result.changes[:30]:
            logger.info("  %s", line)
        if len(result.changes) > 30:
            logger.info("  … ещё %s изменений", len(result.changes) - 30)
        raise SystemExit(0)
