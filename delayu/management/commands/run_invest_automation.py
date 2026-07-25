"""Периодический runner автоматизации инвестконтура."""
from django.core.management.base import BaseCommand

from delayu.models import Subsystem
from delayu.services.invest_flags import ensure_automation_config
from delayu.services.invest_journal import requeue_dead_letters
from delayu.services.invest_pipeline import run_scheduled_automation


class Command(BaseCommand):
    help = "Run invest automation: SLA escalations, metrics, dead-letter requeue"

    def add_arguments(self, parser):
        parser.add_argument("--subsystem", default="invest-kk")
        parser.add_argument("--requeue-dead", action="store_true")

    def handle(self, *args, **options):
        sub = Subsystem.objects.filter(code=options["subsystem"], industry_template="invest").first()
        if not sub:
            self.stderr.write(self.style.ERROR("subsystem not found"))
            return
        ensure_automation_config(sub)
        if options["requeue_dead"]:
            n = requeue_dead_letters(subsystem=sub)
            self.stdout.write(f"requeued dead letters: {n}")
        result = run_scheduled_automation(subsystem=sub)
        self.stdout.write(self.style.SUCCESS(str(result)))
