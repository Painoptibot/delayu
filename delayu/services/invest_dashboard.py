"""Leadership dashboard metrics for the invest subsystem."""

from datetime import datetime, time, timedelta

from django.db.models import Count, Q, Sum
from django.utils import timezone

from delayu.models_invest import InvestPackage, InvestPackageItem, InvestProject, InvestProjectSite, InvestRoadmapItem


def _stage_counts(subsystem, funnel: str) -> dict[str, int]:
    rows = (
        InvestProject.objects.filter(subsystem=subsystem, funnel=funnel)
        .values("stage")
        .annotate(total=Count("id"))
        .order_by("stage")
    )
    return {row["stage"]: row["total"] for row in rows}


def _overdue_roadmap_items(subsystem):
    now = timezone.now()
    return InvestRoadmapItem.objects.filter(project__subsystem=subsystem).filter(
        Q(status=InvestRoadmapItem.Status.OVERDUE)
        | Q(status=InvestRoadmapItem.Status.OPEN, due_at__lt=now)
    )


def _packages_ready_pct(subsystem) -> int:
    packages = InvestPackage.objects.filter(project__subsystem=subsystem, is_active=True)
    total = packages.count()
    if total == 0:
        return 0

    ready = (
        packages.annotate(
            missing_required=Count(
                "items",
                filter=Q(items__required=True, items__status=InvestPackageItem.Status.MISSING),
            )
        )
        .filter(missing_required=0)
        .count()
    )
    return round(ready * 100 / total)


def _industry_metrics(subsystem):
    rows = (
        InvestProject.objects.filter(subsystem=subsystem)
        .values("industry")
        .annotate(
            projects=Count("id"),
            investment_amount=Sum("investment_amount"),
            jobs=Sum("jobs_count"),
        )
        .order_by("-projects", "industry")
    )
    return [
        {
            "industry": row["industry"] or "Без отрасли",
            "projects": row["projects"],
            "investment_amount": float(row["investment_amount"] or 0),
            "jobs": row["jobs"] or 0,
        }
        for row in rows
    ]


def _as_aware_start(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.combine(value, time.min)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _as_aware_end(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.combine(value, time.max)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _period_window(*, period: str = "", date_from=None, date_to=None, now=None):
    now = now or timezone.now()
    if date_from or date_to:
        start = _as_aware_start(date_from) or timezone.make_aware(datetime.combine(now.date(), time.min))
        end = _as_aware_end(date_to) or now
    elif period == "month":
        start = now - timedelta(days=30)
        end = now
    else:
        period = "week"
        start = now - timedelta(days=7)
        end = now
    previous_end = start
    previous_start = previous_end - (end - start)
    return period, start, end, previous_start, previous_end


def _period_compare(subsystem, *, period: str = "", date_from=None, date_to=None, now=None):
    period, start, end, previous_start, previous_end = _period_window(
        period=period,
        date_from=date_from,
        date_to=date_to,
        now=now,
    )
    projects = InvestProject.objects.filter(subsystem=subsystem)
    return {
        "period": period,
        "from": start.date(),
        "to": end.date(),
        "current_count": projects.filter(created_at__gte=start, created_at__lte=end).count(),
        "previous_count": projects.filter(created_at__gte=previous_start, created_at__lt=previous_end).count(),
    }


def build_dashboard(subsystem, *, period: str = "", date_from=None, date_to=None, now=None) -> dict:
    overdue = _overdue_roadmap_items(subsystem)
    industry_metrics = _industry_metrics(subsystem)
    bottlenecks = (
        overdue.values("project__organization_id", "project__organization__name")
        .annotate(overdue_count=Count("id"))
        .order_by("-overdue_count", "project__organization__name")[:5]
    )
    return {
        "attraction_counts": _stage_counts(subsystem, InvestProject.Funnel.ATTRACTION),
        "support_counts": _stage_counts(subsystem, InvestProject.Funnel.SUPPORT),
        "overdue_count": overdue.count(),
        "packages_ready_pct": _packages_ready_pct(subsystem),
        "industry_metrics": industry_metrics,
        "investment_total": sum(row["investment_amount"] for row in industry_metrics),
        "jobs_total": sum(row["jobs"] for row in industry_metrics),
        "period_compare": _period_compare(
            subsystem,
            period=period,
            date_from=date_from,
            date_to=date_to,
            now=now,
        ),
        "active_bookings": InvestProjectSite.objects.filter(
            project__subsystem=subsystem,
            role=InvestProjectSite.Role.BOOKED,
        ).count(),
        "bottlenecks_by_org": [
            {
                "organization_id": row["project__organization_id"],
                "organization_name": row["project__organization__name"],
                "overdue_count": row["overdue_count"],
            }
            for row in bottlenecks
        ],
    }
