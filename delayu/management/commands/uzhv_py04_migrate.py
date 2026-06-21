"""PY-04 — миграция данных по mapping.json."""
from pathlib import Path

from django.core.management.base import BaseCommand

from delayu.management.subsystem_cli import filter_subsystems
from delayu.models import Subsystem
from delayu.services.uzhv_migration import load_mapping, migrate_from_mapping
from delayu.services.uzhv_py_cli import EXIT_CONFIG, EXIT_VALIDATION, setup_py_logger


class Command(BaseCommand):
    help = "PY-04: миграция CSV по mapping.json / mapping.yaml"

    def add_arguments(self, parser):
        parser.add_argument("source", help="Исходный CSV")
        parser.add_argument("mapping", help="mapping.json или mapping.yaml")
        parser.add_argument("--subsystem", default="uzhv")
        parser.add_argument("--log-file", default="")

    def handle(self, *args, **options):
        logger = setup_py_logger("py04", options["log_file"] or None)
        src = Path(options["source"])
        map_path = Path(options["mapping"])
        if not src.is_file() or not map_path.is_file():
            logger.error("Проверьте пути source и mapping")
            raise SystemExit(EXIT_CONFIG)

        subs = filter_subsystems(
            Subsystem.objects.all(), options["subsystem"], stdout=self.stdout, style=self.style
        )
        if subs is None or not subs:
            raise SystemExit(EXIT_CONFIG)

        try:
            mapping = load_mapping(map_path)
        except (RuntimeError, ValueError) as exc:
            logger.error("%s", exc)
            raise SystemExit(EXIT_CONFIG) from exc

        result = migrate_from_mapping(subs[0], mapping, src)
        logger.info("Создано: %s, пропущено: %s", result.created, result.skipped)
        for err in result.errors:
            logger.error(err)
        raise SystemExit(EXIT_VALIDATION if result.errors else 0)
