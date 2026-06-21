"""#31 — запуск отчётов по расписанию."""
from django.core.management.base import BaseCommand

from delayu.models import Subsystem
from delayu.services.report_schedules import run_due_schedules, run_schedule


class Command(BaseCommand):
    help = "Запускает просроченные расписания отчётов (M16)"

    def add_arguments(self, parser):
        parser.add_argument("--subsystem", default="")
        parser.add_argument("--force-id", type=int, default=0, help="Запустить конкретное расписание")

    def handle(self, *args, **options):
        sub_code = (options.get("subsystem") or "").strip()
        sub = Subsystem.objects.filter(code=sub_code).first() if sub_code else None
        force_id = options.get("force_id") or 0
        if force_id:
            from delayu.models import ReportSchedule

            sched = ReportSchedule.objects.select_related("template", "subsystem").get(pk=force_id)
            run = run_schedule(sched)
            self.stdout.write(self.style.SUCCESS(f"Schedule #{force_id} -> run #{run.pk}"))
            return
        runs = run_due_schedules(subsystem=sub)
        self.stdout.write(self.style.SUCCESS(f"Executed {len(runs)} schedule(s)"))
