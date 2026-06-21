"""M35 — SLA и эскалации."""
from datetime import timedelta

from django.utils import timezone

from delayu.models import BPMTask, CaseFile, SLARule


def filter_sla_rules(subsystem, *, active_only=False):
    qs = SLARule.objects.filter(subsystem=subsystem).select_related("escalate_to")
    if active_only:
        qs = qs.filter(is_active=True)
    return qs.order_by("code")


def sla_monitor_metrics(subsystem):
    rule = SLARule.objects.filter(subsystem=subsystem, is_active=True).first()
    hours = rule.hours_limit if rule else 72
    threshold = timezone.now() - timedelta(hours=hours)
    cases = CaseFile.objects.filter(subsystem=subsystem, is_archived=False)
    total = cases.count()
    overdue = cases.filter(due_date__lt=timezone.now().date()).count()
    at_risk = cases.filter(
        due_date__isnull=False,
        due_date__gte=timezone.now().date(),
        due_date__lte=(timezone.now() + timedelta(days=3)).date(),
    ).count()
    stale = cases.filter(
        created_at__lt=threshold,
        status__in=[CaseFile.Status.NEW, CaseFile.Status.IN_PROGRESS],
    ).count()
    bpm_stuck = BPMTask.objects.filter(
        instance__case__subsystem=subsystem,
        status=BPMTask.Status.PENDING,
        decided_at__isnull=True,
    ).count()
    return {
        "rule": rule,
        "hours_limit": hours,
        "total_cases": total,
        "overdue_cases": overdue,
        "at_risk_cases": at_risk,
        "stale_cases": stale,
        "bpm_pending": bpm_stuck,
    }


def cases_for_escalation(subsystem, limit=20):
    rule = SLARule.objects.filter(subsystem=subsystem, is_active=True).first()
    if not rule:
        return CaseFile.objects.none()
    return (
        CaseFile.objects.filter(
            subsystem=subsystem,
            is_archived=False,
            due_date__lt=timezone.now().date(),
        )
        .select_related("assignee")[:limit]
    )
