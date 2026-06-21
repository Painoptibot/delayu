"""PY-02 — пакетное формирование отчётов ОТЧ в каталог."""
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand

from delayu.management.subsystem_cli import filter_subsystems
from delayu.models import Subsystem
from delayu.services.uzhv_export import build_report_rows, rows_to_xlsx_bytes
from delayu.services.uzhv_py_cli import EXIT_CONFIG, setup_py_logger
from delayu.services.uzhv_reports import REPORT_BUILDERS


class Command(BaseCommand):
    help = "PY-02: пакетный экспорт отчётов УЖВ (CSV/XLSX) в каталог"

    def add_arguments(self, parser):
        parser.add_argument("--subsystem", default="uzhv")
        parser.add_argument("--output", default="media/uzhv_exports", help="Каталог выгрузки")
        parser.add_argument("--format", choices=("csv", "xlsx", "both"), default="both")
        parser.add_argument("--codes", default="", help="Коды через запятую (пусто = все ОТЧ)")
        parser.add_argument("--from", dest="period_from", default="", help="YYYY-MM-DD")
        parser.add_argument("--to", dest="period_to", default="", help="YYYY-MM-DD")
        parser.add_argument("--log-file", default="")

    def handle(self, *args, **options):
        logger = setup_py_logger("py02", options["log_file"] or None)
        subs = filter_subsystems(
            Subsystem.objects.all(), options["subsystem"], stdout=self.stdout, style=self.style
        )
        if subs is None or not subs:
            raise SystemExit(EXIT_CONFIG)
        sub = subs[0]

        out_root = Path(options["output"]) / sub.code
        out_root.mkdir(parents=True, exist_ok=True)

        codes = [c.strip() for c in options["codes"].split(",") if c.strip()] or [
            k for k in REPORT_BUILDERS if k.startswith("otch-")
        ]
        p_start = date.fromisoformat(options["period_from"]) if options["period_from"] else None
        p_end = date.fromisoformat(options["period_to"]) if options["period_to"] else None
        fmt = options["format"]
        written = 0

        for code in codes:
            if code not in REPORT_BUILDERS:
                logger.warning("Неизвестный код отчёта: %s", code)
                continue
            title, rows = build_report_rows(
                code, sub, period_start=p_start, period_end=p_end
            )
            if fmt in ("csv", "both"):
                csv_path = out_root / f"{code}.csv"
                lines = [";".join(row) for row in rows]
                csv_path.write_text("\n".join(lines), encoding="utf-8-sig")
                logger.info("CSV: %s (%s)", csv_path, title)
                written += 1
            if fmt in ("xlsx", "both"):
                xlsx_path = out_root / f"{code}.xlsx"
                xlsx_path.write_bytes(rows_to_xlsx_bytes(rows, sheet_title=title[:31]))
                logger.info("XLSX: %s", xlsx_path)
                written += 1

        logger.info("Готово: %s файлов в %s", written, out_root)
        raise SystemExit(0)
