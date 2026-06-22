"""Метрики узлов BPM по истории задач (#19)."""
from __future__ import annotations

from django.db.models import Count, Q
from django.utils import timezone

from delayu.models import BPMTask, BPMTemplate


def template_node_metrics(template: BPMTemplate) -> dict[str, dict]:
    """Сводка по step_id для шаблона."""
    qs = BPMTask.objects.filter(instance__template=template)
    by_step = qs.values("step_id").annotate(
        total=Count("id"),
        pending=Count("id", filter=Q(status=BPMTask.Status.PENDING)),
        done=Count("id", filter=Q(status=BPMTask.Status.DONE)),
        rejected=Count("id", filter=Q(status=BPMTask.Status.REJECTED)),
    )
    metrics: dict[str, dict] = {}
    cutoff = timezone.now() - timezone.timedelta(days=2)
    for row in by_step:
        sid = row["step_id"]
        pending_count = row["pending"] or 0
        overdue = 0
        if pending_count:
            overdue = qs.filter(
                step_id=sid,
                status=BPMTask.Status.PENDING,
                instance__started_at__lt=cutoff,
            ).count()
        avg_hours = None
        done_qs = qs.filter(step_id=sid, status=BPMTask.Status.DONE, decided_at__isnull=False)
        if done_qs.exists():
            durations = []
            for task in done_qs.select_related("instance")[:500]:
                start = task.instance.started_at
                if start and task.decided_at:
                    hours = (task.decided_at - start).total_seconds() / 3600
                    durations.append(max(hours, 0.1))
            if durations:
                avg_hours = round(sum(durations) / len(durations), 1)
        total = row["total"] or 0
        metrics[sid] = {
            "total": total,
            "pending": pending_count,
            "done": row["done"] or 0,
            "rejected": row["rejected"] or 0,
            "avg_hours": avg_hours,
            "overdue_pct": round(100 * overdue / pending_count, 0) if pending_count else 0,
        }
    return metrics
