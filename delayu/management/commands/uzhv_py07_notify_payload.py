"""PY-07 — заготовка JSON payload для уведомлений (I-06)."""
from pathlib import Path

from django.core.management.base import BaseCommand

from delayu.management.subsystem_cli import filter_subsystems
from delayu.models import Subsystem
from delayu.services.uzhv_notify_payload import build_notify_payloads
from delayu.services.uzhv_py_cli import EXIT_CONFIG, setup_py_logger


class Command(BaseCommand):
    help = "PY-07: формирование JSON-файлов событий для последующей отправки"

    def add_arguments(self, parser):
        parser.add_argument("--subsystem", default="uzhv")
        parser.add_argument(
            "--output",
            default="media/uzhv_notify_queue",
            help="Каталог для JSON payload",
        )
        parser.add_argument("--days-ahead", type=int, default=3, help="Горизонт сроков (дней)")
        parser.add_argument("--log-file", default="")

    def handle(self, *args, **options):
        logger = setup_py_logger("py07", options["log_file"] or None)
        subs = filter_subsystems(
            Subsystem.objects.all(), options["subsystem"], stdout=self.stdout, style=self.style
        )
        if subs is None or not subs:
            raise SystemExit(EXIT_CONFIG)

        out_dir = Path(options["output"]) / subs[0].code
        result = build_notify_payloads(
            subs[0], out_dir, days_ahead=options["days_ahead"]
        )
        logger.info("Сформировано payload: %s → %s", result.count, out_dir)
        for f in result.files[:10]:
            logger.info("  %s", f)
        if len(result.files) > 10:
            logger.info("  … ещё %s файлов", len(result.files) - 10)
        raise SystemExit(0)
