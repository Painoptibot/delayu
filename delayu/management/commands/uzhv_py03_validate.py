"""PY-03 — валидация СНИЛС и паспортных полей в CSV."""
from pathlib import Path

from django.core.management.base import BaseCommand

from delayu.services.uzhv_py_cli import EXIT_CONFIG, EXIT_VALIDATION, setup_py_logger
from delayu.services.uzhv_validation import validate_citizens_csv, validation_report_csv


class Command(BaseCommand):
    help = "PY-03: проверка CSV граждан перед импортом"

    def add_arguments(self, parser):
        parser.add_argument("file", help="CSV с колонками snils / passport_series / passport_number")
        parser.add_argument("--report", default="", help="Путь к отчёту об ошибках (CSV)")
        parser.add_argument("--log-file", default="")

    def handle(self, *args, **options):
        logger = setup_py_logger("py03", options["log_file"] or None)
        path = Path(options["file"])
        if not path.is_file():
            logger.error("Файл не найден: %s", path)
            raise SystemExit(EXIT_CONFIG)

        raw = path.read_bytes()
        content = None
        for enc in ("utf-8-sig", "utf-8", "cp1251"):
            try:
                content = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if content is None:
            logger.error("Не удалось прочитать кодировку")
            raise SystemExit(EXIT_CONFIG)

        report = validate_citizens_csv(content)
        logger.info(
            "Строк: %s, без ошибок: %s, ошибок: %s",
            report.total_rows,
            report.valid_rows,
            len(report.errors),
        )
        for err in report.errors[:50]:
            logger.warning("Строка %s [%s]: %s", err.row, err.field, err.message)
        if len(report.errors) > 50:
            logger.warning("… и ещё %s ошибок", len(report.errors) - 50)

        if options["report"]:
            Path(options["report"]).write_text(validation_report_csv(report), encoding="utf-8-sig")
            logger.info("Отчёт: %s", options["report"])

        raise SystemExit(EXIT_VALIDATION if not report.ok else 0)
