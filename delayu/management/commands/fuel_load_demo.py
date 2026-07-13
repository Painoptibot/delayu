"""Нагрузочное тестирование и проверка здоровья контура «Топливный пропуск»."""
from django.core.management.base import BaseCommand

from delayu.models import Subsystem
from delayu.services.fuel_health import fuel_health_report, run_load_demo


class Command(BaseCommand):
    help = "Проверка компонентов и нагрузочный тест портала топливного пропуска"

    def add_arguments(self, parser):
        parser.add_argument("--subsystem", default="novorossiysk", help="Код или subdomain подсистемы")
        parser.add_argument("--requests", type=int, default=20, help="Запросов на каждый endpoint")
        parser.add_argument("--workers", type=int, default=8, help="Параллельных потоков")
        parser.add_argument("--skip-load", action="store_true", help="Только health-check")

    def handle(self, *args, **options):
        code = options["subsystem"]
        sub = (
            Subsystem.objects.filter(public_subdomain=code).first()
            or Subsystem.objects.filter(code=code).first()
        )
        if not sub:
            self.stderr.write(self.style.ERROR(f"Подсистема не найдена: {code}"))
            return

        health = fuel_health_report(sub)
        self.stdout.write(self.style.SUCCESS("=== Health ==="))
        self.stdout.write(f"OK: {health['ok']}")
        for name, comp in health["components"].items():
            status = "OK" if comp.get("ok") else "FAIL"
            self.stdout.write(f"  {name}: {status} ({comp.get('ms', '—')} ms)")
        for key, val in health["counts"].items():
            self.stdout.write(f"  {key}: {val}")

        if options["skip_load"]:
            return

        load = run_load_demo(sub, requests_per_endpoint=options["requests"], workers=options["workers"])
        self.stdout.write(self.style.SUCCESS("=== Load test ==="))
        self.stdout.write(f"Requests: {load['total_requests']}, success: {load['success_count']}")
        self.stdout.write(f"Duration: {load['duration_ms']} ms, RPS: {load['rps']}, p95: {load['p95_ms']} ms")
        for path, stats in load["per_endpoint"].items():
            self.stdout.write(f"  {path}: avg {stats['avg_ms']} ms, max {stats['max_ms']} ms")
