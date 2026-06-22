"""Планировщик без Celery (Windows/Laragon): отчёты + очередь интеграций."""
from __future__ import annotations

from delayu.models import Subsystem
from delayu.services.bpm_escalation import process_bpm_escalations
from delayu.services.integrations import process_pending_queue
from delayu.services.report_schedules import run_due_schedules
from delayu.services.siem_export import push_siem_events
from delayu.services.studio_activity_schedule import process_due_studio_activity_digests
from delayu.services.studio_compliance_schedule import process_due_studio_compliance_exports
from delayu.services.studio_publish_schedule import process_due_scheduled_publishes


def run_all_scheduled(*, subsystem_code: str = "", limit: int = 50) -> dict:
    sub = Subsystem.objects.filter(code=subsystem_code).first() if subsystem_code else None
    reports = run_due_schedules(subsystem=sub)
    queue = process_pending_queue(sub, limit=limit) if sub else {"processed": 0, "success": 0, "failed": 0}
    bpm_esc = {"escalated": 0, "checked": 0}
    siem = {"pushed": 0, "ok": True}
    if not sub and subsystem_code:
        return {"error": f"subsystem {subsystem_code} not found"}
    if sub:
        bpm_esc = process_bpm_escalations(sub, limit=limit)
        siem = push_siem_events(sub, limit=limit)
    elif not sub:
        total_queue = {"processed": 0, "success": 0, "failed": 0}
        total_bpm = {"escalated": 0, "checked": 0}
        total_siem = {"pushed": 0}
        for s in Subsystem.objects.filter(status=Subsystem.Status.ACTIVE):
            r = process_pending_queue(s, limit=limit)
            total_queue["processed"] += r["processed"]
            total_queue["success"] += r["success"]
            total_queue["failed"] += r["failed"]
            e = process_bpm_escalations(s, limit=limit)
            total_bpm["escalated"] += e.get("escalated", 0)
            total_bpm["checked"] += e.get("checked", 0)
            s_res = push_siem_events(s, limit=limit)
            if s_res.get("ok"):
                total_siem["pushed"] += s_res.get("pushed", 0)
        queue = total_queue
        bpm_esc = total_bpm
        siem = total_siem
    studio_publish = process_due_scheduled_publishes(limit=limit)
    studio_digest = process_due_studio_activity_digests(limit=limit)
    studio_compliance = process_due_studio_compliance_exports(limit=limit)
    return {
        "report_runs": len(reports),
        "queue": queue,
        "bpm_escalations": bpm_esc,
        "siem": siem,
        "studio_publish": studio_publish,
        "studio_activity_digest": studio_digest,
        "studio_compliance_export": studio_compliance,
        "subsystem": sub.code if sub else "all",
    }
