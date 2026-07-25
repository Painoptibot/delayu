"""Leadership dashboard metrics for the invest subsystem."""

from datetime import datetime, time, timedelta

from django.db.models import Count, Q, Sum
from django.utils import timezone

from delayu.models_invest import (
    InvestPackage,
    InvestPackageItem,
    InvestProject,
    InvestProjectSite,
    InvestQuarterTarget,
    InvestRoadmapItem,
)


def _stage_counts(subsystem, funnel: str) -> dict[str, int]:
    rows = (
        InvestProject.objects.filter(subsystem=subsystem, funnel=funnel)
        .values("stage")
        .annotate(total=Count("id"))
        .order_by("stage")
    )
    return {row["stage"]: row["total"] for row in rows}


def _overdue_roadmap_items(subsystem, *, now=None):
    now = now or timezone.now()
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


def _risk_rank(risk: str) -> int:
    return {"high": 2, "medium": 1}.get(risk, 0)


def _roadmap_item_risk(item, *, now=None) -> str:
    now = now or timezone.now()
    if item.status == InvestRoadmapItem.Status.DONE:
        return "low"
    if item.status == InvestRoadmapItem.Status.OVERDUE:
        return "high"
    if item.due_at and item.due_at < now:
        return "high"
    if item.due_at and item.due_at <= now + timedelta(days=3):
        return "medium"
    return "low"


def project_sla_risk(project, *, now=None) -> dict:
    now = now or timezone.now()
    risks = []
    for item in project.roadmap_items.exclude(status=InvestRoadmapItem.Status.DONE).order_by("due_at", "code"):
        risk = _roadmap_item_risk(item, now=now)
        if risk == "low":
            continue
        risks.append(
            {
                "code": item.code,
                "title": item.title,
                "due_at": item.due_at,
                "status": item.status,
                "risk": risk,
            }
        )
    risk = "low"
    if risks:
        risk = max((row["risk"] for row in risks), key=_risk_rank)
    labels = {"high": "Высокий SLA risk", "medium": "Средний SLA risk", "low": "SLA risk низкий"}
    return {
        "risk": risk,
        "label": labels[risk],
        "items": risks,
        "items_count": len(risks),
    }


def _sla_risk_summary(subsystem, *, now=None):
    now = now or timezone.now()
    due_limit = now + timedelta(days=3)
    items = (
        InvestRoadmapItem.objects.filter(project__subsystem=subsystem)
        .exclude(status=InvestRoadmapItem.Status.DONE)
        .filter(Q(status=InvestRoadmapItem.Status.OVERDUE) | Q(due_at__lte=due_limit))
        .select_related("project", "project__organization")
        .order_by("due_at", "code")
    )
    projects = {}
    high_count = 0
    medium_count = 0
    for item in items:
        risk = _roadmap_item_risk(item, now=now)
        if risk == "low":
            continue
        if risk == "high":
            high_count += 1
        elif risk == "medium":
            medium_count += 1
        row = projects.setdefault(
            item.project_id,
            {
                "project_id": item.project_id,
                "project_code": item.project.code,
                "project_name": item.project.name,
                "organization_name": item.project.organization.name,
                "risk": risk,
                "items_count": 0,
            },
        )
        row["items_count"] += 1
        if _risk_rank(risk) > _risk_rank(row["risk"]):
            row["risk"] = risk
    return {
        "high_count": high_count,
        "medium_count": medium_count,
        "projects": sorted(projects.values(), key=lambda row: (-_risk_rank(row["risk"]), row["project_code"]))[:10],
    }


def _quarter_bounds(year: int, quarter: int):
    start_month = (quarter - 1) * 3 + 1
    start = timezone.make_aware(datetime(year, start_month, 1, 0, 0, 0))
    if quarter == 4:
        end = timezone.make_aware(datetime(year + 1, 1, 1, 0, 0, 0))
    else:
        end = timezone.make_aware(datetime(year, start_month + 3, 1, 0, 0, 0))
    return start, end


def _quarter_target_progress(subsystem, *, now=None):
    now = now or timezone.now()
    quarter = ((now.month - 1) // 3) + 1
    target = InvestQuarterTarget.objects.filter(subsystem=subsystem, year=now.year, quarter=quarter).first()
    goal = target.attraction_goal if target else 0
    start, end = _quarter_bounds(now.year, quarter)
    actual = InvestProject.objects.filter(subsystem=subsystem, created_at__gte=start, created_at__lt=end).count()
    progress_pct = round(actual * 100 / goal) if goal else 0
    return {
        "year": now.year,
        "quarter": quarter,
        "goal": goal,
        "actual": actual,
        "progress_pct": min(progress_pct, 100),
    }


def build_dashboard(subsystem, *, period: str = "", date_from=None, date_to=None, now=None) -> dict:
    overdue = _overdue_roadmap_items(subsystem, now=now)
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


def build_cockpit(subsystem, *, now=None, period: str = "", date_from=None, date_to=None) -> dict:
    dashboard = build_dashboard(subsystem, period=period, date_from=date_from, date_to=date_to, now=now)
    projects = InvestProject.objects.filter(subsystem=subsystem)
    return {
        "dashboard": dashboard,
        "kpis": {
            "projects_total": projects.count(),
            "attraction": projects.filter(funnel=InvestProject.Funnel.ATTRACTION).count(),
            "support": projects.filter(funnel=InvestProject.Funnel.SUPPORT).count(),
            "overdue": dashboard["overdue_count"],
            "packages_ready_pct": dashboard["packages_ready_pct"],
            "active_bookings": dashboard["active_bookings"],
        },
        "sla_risk": _sla_risk_summary(subsystem, now=now),
        "heat_by_mo": dashboard["bottlenecks_by_org"],
        "quarter_target": _quarter_target_progress(subsystem, now=now),
        "heat_note": "Yandex heat later",
    }
