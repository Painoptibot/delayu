"""Планировщик: отчёты + очередь интеграций (без Celery)."""
from django.core.management.base import BaseCommand

from delayu.services.scheduled_tasks import run_all_scheduled


class Command(BaseCommand):
    help = "Запускает due report schedules и обработку очереди интеграций"

    def add_arguments(self, parser):
        parser.add_argument("--subsystem", default="pilot")
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        result = run_all_scheduled(
            subsystem_code=options.get("subsystem") or "",
            limit=options.get("limit") or 50,
        )
        if result.get("error"):
            self.stderr.write(result["error"])
            return
        self.stdout.write(self.style.SUCCESS(str(result)))
