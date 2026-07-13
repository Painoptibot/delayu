"""
Восстановление деплоя Студии на prod: колонки studio_* уже в БД, а 0051 не записана.

  python manage.py repair_studio_migrations
  python manage.py repair_studio_migrations --dry-run
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder


def _column_exists(table: str, column: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
            LIMIT 1
            """,
            [table, column],
        )
        return cursor.fetchone() is not None


def _table_exists(table: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", [f"public.{table}"])
        return cursor.fetchone()[0] is not None


class Command(BaseCommand):
    help = "Убрать «осиротевшие» колонки Студии и прогнать migrate (prod fix)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только диагностика, без изменений",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        recorder = MigrationRecorder(connection)
        applied = set(recorder.applied_migrations())
        need_0051 = ("delayu", "0051_studio_wave1") not in applied

        cols = {
            name: _column_exists("delayu_subsystem", name)
            for name in ("studio_draft", "studio_has_draft", "studio_setup_state")
        }
        tables = {
            "delayu_rolestutiolayout": _table_exists("delayu_rolestutiolayout"),
            "delayu_studioconfigrevision": _table_exists("delayu_studioconfigrevision"),
        }

        self.stdout.write(f"0051 применена: {not need_0051}")
        self.stdout.write(f"Колонки delayu_subsystem: {cols}")
        self.stdout.write(f"Таблицы Студии: {tables}")

        orphan_columns = need_0051 and (
            cols["studio_draft"] or cols["studio_has_draft"]
        ) and not tables["delayu_studioconfigrevision"]

        if orphan_columns:
            drops = []
            if cols["studio_draft"]:
                drops.append("ALTER TABLE delayu_subsystem DROP COLUMN IF EXISTS studio_draft")
            if cols["studio_has_draft"]:
                drops.append("ALTER TABLE delayu_subsystem DROP COLUMN IF EXISTS studio_has_draft")
            self.stdout.write(
                self.style.WARNING(
                    "Обнаружены колонки без таблиц ревизий — удаляем и прогоняем migrate:"
                )
            )
            for sql in drops:
                self.stdout.write(f"  {sql}")
                if not dry_run:
                    with connection.cursor() as cursor:
                        cursor.execute(sql)
        elif need_0051 and tables["delayu_studioconfigrevision"]:
            self.stdout.write(
                self.style.WARNING(
                    "Схема 0051 уже есть — помечаем migrate --fake delayu 0051"
                )
            )
            if not dry_run:
                call_command("migrate", "delayu", "0051", fake=True, verbosity=1)

        if dry_run:
            self.stdout.write("[dry-run] migrate не запускался")
            return

        call_command("migrate", verbosity=1)
        self.stdout.write(self.style.SUCCESS("migrate завершён"))
