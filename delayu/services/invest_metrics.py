"""Метрики автоматизации (п.30)."""
from __future__ import annotations

from django.utils import timezone

from delayu.models_invest import (
    InvestAutomationRun,
    InvestExternalTask,
    InvestIntegrationEvent,
    InvestProject,
    InvestSmevRequest,
)


def collect_metrics(*, subsystem) -> dict:
    projects = InvestProject.objects.filter(subsystem=subsystem)
    autofill_hits = 0
    total_fields = 0
    for project in projects.iterator():
        ext = project.external_ids or {}
        total_fields += 1
        if ext.get("completeness_pct", 0) >= 60:
            autofill_hits += 1
    smev_applied = InvestSmevRequest.objects.filter(
        subsystem=subsystem, status=InvestSmevRequest.Status.APPLIED
    ).count()
    outbound = InvestIntegrationEvent.objects.filter(
        subsystem=subsystem,
        channel=InvestIntegrationEvent.Channel.BITRIX,
        direction=InvestIntegrationEvent.Direction.OUT,
        status=InvestIntegrationEvent.Status.DONE,
        event_type="deal.push",
    )
    inbound = InvestIntegrationEvent.objects.filter(
        subsystem=subsystem,
        channel=InvestIntegrationEvent.Channel.BITRIX,
        direction=InvestIntegrationEvent.Direction.IN,
        event_type="deal.upsert",
        status=InvestIntegrationEvent.Status.DONE,
    )
    mo_overdue = InvestExternalTask.objects.filter(
        subsystem=subsystem, kind=InvestExternalTask.Kind.MO, status=InvestExternalTask.Status.OVERDUE
    ).count()
    tp_overdue = InvestExternalTask.objects.filter(
        subsystem=subsystem, kind=InvestExternalTask.Kind.TP, status=InvestExternalTask.Status.OVERDUE
    ).count()
    return {
        "projects_total": projects.count(),
        "autofilled_share_pct": int(100 * autofill_hits / total_fields) if total_fields else 0,
        "smev_applied": smev_applied,
        "bitrix_inbound_done": inbound.count(),
        "bitrix_outbound_done": outbound.count(),
        "mo_overdue": mo_overdue,
        "tp_overdue": tp_overdue,
        "ready_for_bitrix": projects.filter(external_ids__ready_for_bitrix=True).count(),
        "collected_at": timezone.now().isoformat(),
    }


def snapshot_metrics(*, subsystem, notes: str = "") -> InvestAutomationRun:
    run = InvestAutomationRun.objects.create(subsystem=subsystem, notes=notes, metrics={})
    metrics = collect_metrics(subsystem=subsystem)
    run.metrics = metrics
    run.finished_at = timezone.now()
    run.save(update_fields=["metrics", "finished_at"])
    return run
