"""Leadership dashboard metrics for the invest subsystem."""

from django.db.models import Count, Q
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


def build_dashboard(subsystem) -> dict:
    overdue = _overdue_roadmap_items(subsystem)
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
