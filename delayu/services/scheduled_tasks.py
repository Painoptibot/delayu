"""Планировщик без Celery (Windows/Laragon): отчёты + очередь интеграций."""
from __future__ import annotations

from delayu.models import Subsystem
from delayu.services.integrations import process_pending_queue
from delayu.services.report_schedules import run_due_schedules


def run_all_scheduled(*, subsystem_code: str = "", limit: int = 50) -> dict:
    sub = Subsystem.objects.filter(code=subsystem_code).first() if subsystem_code else None
    reports = run_due_schedules(subsystem=sub)
    queue = process_pending_queue(sub, limit=limit) if sub else {"processed": 0, "success": 0, "failed": 0}
    if not sub and subsystem_code:
        return {"error": f"subsystem {subsystem_code} not found"}
    if not sub:
        total_queue = {"processed": 0, "success": 0, "failed": 0}
        for s in Subsystem.objects.filter(status=Subsystem.Status.ACTIVE):
            r = process_pending_queue(s, limit=limit)
            total_queue["processed"] += r["processed"]
            total_queue["success"] += r["success"]
            total_queue["failed"] += r["failed"]
        queue = total_queue
    return {
        "report_runs": len(reports),
        "queue": queue,
        "subsystem": sub.code if sub else "all",
    }
