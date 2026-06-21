"""PY-01 — импорт справочников и реестров (CSV жилфонд, XLSX договоры)."""
from pathlib import Path

from django.core.management.base import BaseCommand

from delayu.management.subsystem_cli import filter_subsystems
from delayu.models import Subsystem
from delayu.services.uzhv_fund_import import FundImportResult, import_registry_file
from delayu.services.uzhv_import import ImportResult
from delayu.services.uzhv_py_cli import EXIT_CONFIG, EXIT_VALIDATION, setup_py_logger


class Command(BaseCommand):
    help = "PY-01: импорт CSV (жилфонд) или XLSX (договоры) в АИС УЖВ"

    def add_arguments(self, parser):
        parser.add_argument("file", help="Путь к CSV или XLSX")
        parser.add_argument("--subsystem", default="uzhv", help="Код подсистемы")
        parser.add_argument(
            "--kind",
            choices=("auto", "fund", "contracts"),
            default="auto",
            help="Тип импорта",
        )
        parser.add_argument("--log-file", default="", help="Файл лога")

    def handle(self, *args, **options):
        logger = setup_py_logger("py01", options["log_file"] or None)
        path = Path(options["file"])
        if not path.is_file():
            logger.error("Файл не найден: %s", path)
            raise SystemExit(EXIT_CONFIG)

        subs = filter_subsystems(
            Subsystem.objects.all(), options["subsystem"], stdout=self.stdout, style=self.style
        )
        if subs is None or not subs:
            raise SystemExit(EXIT_CONFIG)
        sub = subs[0]

        result = import_registry_file(sub, path, kind=options["kind"])
        if isinstance(result, FundImportResult):
            logger.info(
                "Жилфонд: МКД +%s ~%s, помещения +%s ~%s",
                result.buildings_created,
                result.buildings_updated,
                result.premises_created,
                result.premises_updated,
            )
            for err in result.errors:
                logger.error(err)
            raise SystemExit(EXIT_VALIDATION if result.errors else 0)

        assert isinstance(result, ImportResult)
        logger.info("Договоры: создано %s, пропущено %s", result.created, result.skipped)
        for err in result.errors:
            logger.error(err)
        raise SystemExit(EXIT_VALIDATION if result.errors else 0)
