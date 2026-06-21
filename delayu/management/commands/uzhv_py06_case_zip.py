"""PY-06 — ZIP-комплект по учётному делу."""
from pathlib import Path

from django.core.management.base import BaseCommand

from delayu.models_uzhv import HousingQueueCase
from delayu.services.uzhv_case_package import build_case_zip_bytes
from delayu.services.uzhv_py_cli import EXIT_CONFIG, setup_py_logger


class Command(BaseCommand):
    help = "PY-06: упаковка manifest.json + summary по ID дела"

    def add_arguments(self, parser):
        parser.add_argument("case_id", type=int, help="ID HousingQueueCase")
        parser.add_argument(
            "--output",
            default="",
            help="Путь к ZIP (по умолчанию media/uzhv_packages/<номер>.zip)",
        )
        parser.add_argument("--log-file", default="")

    def handle(self, *args, **options):
        logger = setup_py_logger("py06", options["log_file"] or None)
        case = HousingQueueCase.objects.filter(pk=options["case_id"]).select_related("citizen").first()
        if not case:
            logger.error("Дело id=%s не найдено", options["case_id"])
            raise SystemExit(EXIT_CONFIG)

        data = build_case_zip_bytes(case)
        if options["output"]:
            out = Path(options["output"])
        else:
            out = Path("media") / "uzhv_packages" / f"{case.case_number.replace('/', '-')}.zip"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        logger.info("Архив: %s (%s байт)", out, len(data))
        raise SystemExit(0)
