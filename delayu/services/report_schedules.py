"""#31 — расписания отчётов M16."""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from delayu.models import ReportRun, ReportSchedule
from delayu.services.analytics import run_report_query

User = get_user_model()


def schedule_is_due(schedule: ReportSchedule, *, now=None) -> bool:
    now = now or timezone.now()
    if not schedule.is_active:
        return False
    if schedule.last_run_at and schedule.last_run_at.date() == now.date():
        if schedule.frequency == ReportSchedule.Frequency.DAILY:
            return False
    if now.hour < schedule.run_hour:
        return False
    if schedule.frequency == ReportSchedule.Frequency.WEEKLY:
        wd = schedule.run_weekday if schedule.run_weekday is not None else 0
        return now.weekday() == wd
    if schedule.frequency == ReportSchedule.Frequency.MONTHLY:
        day = schedule.run_day if schedule.run_day is not None else 1
        return now.day == day
    return True


def due_schedules(subsystem=None):
    qs = ReportSchedule.objects.filter(is_active=True).select_related("template", "subsystem")
    if subsystem:
        qs = qs.filter(subsystem=subsystem)
    return [s for s in qs if schedule_is_due(s)]


def run_schedule(schedule: ReportSchedule, *, user=None) -> ReportRun:
    user = user or schedule.created_by
    if user is None:
        user = User.objects.filter(is_superuser=True).first()
    result = run_report_query(
        schedule.subsystem,
        schedule.template.query_key,
        period_days=schedule.period_days,
    )
    run = ReportRun.objects.create(
        template=schedule.template,
        user=user,
        result=result,
        period_label=f"auto-{schedule.period_days}d",
    )
    schedule.last_run_at = timezone.now()
    schedule.save(update_fields=["last_run_at"])
    return run


def run_due_schedules(*, subsystem=None, user=None) -> list[ReportRun]:
    runs = []
    for sched in due_schedules(subsystem=subsystem):
        runs.append(run_schedule(sched, user=user))
    return runs
