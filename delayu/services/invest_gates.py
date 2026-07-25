"""Gate-правила готовности к обратной выгрузке в Битрикс (п.9, 20)."""
from __future__ import annotations

from delayu.models_invest import InvestExternalTask, InvestPackageItem, InvestProject
from delayu.services.invest_package import ensure_package, package_is_ready


GATE_FIELDS = (
    "name",
    "investor_name",
    "organization_id",
    "industry",
)


def compute_completeness(project: InvestProject) -> int:
    filled = 0
    total = 0
    for field in ("name", "investor_name", "industry", "contact_person", "contact_phone", "description", "support_measures"):
        total += 1
        if getattr(project, field, None):
            filled += 1
    if project.investment_amount is not None:
        filled += 1
    total += 1
    if project.jobs_count is not None:
        filled += 1
    total += 1
    pkg = ensure_package(project)
    required = pkg.items.filter(required=True)
    total += required.count() or 1
    filled += required.exclude(status=InvestPackageItem.Status.MISSING).count()
    return min(100, int(100 * filled / max(total, 1)))


def gate_blockers(project: InvestProject) -> list[str]:
    blockers = []
    for field in GATE_FIELDS:
        if field.endswith("_id"):
            if not getattr(project, field, None):
                blockers.append(field)
        elif not getattr(project, field, None):
            blockers.append(field)
    if not package_is_ready(project):
        blockers.append("package_incomplete")
    open_mo = project.external_tasks.filter(
        kind=InvestExternalTask.Kind.MO,
        status__in=(InvestExternalTask.Status.OPEN, InvestExternalTask.Status.OVERDUE),
    ).exists()
    if open_mo:
        blockers.append("mo_pending")
    return blockers


def can_push_to_bitrix(project: InvestProject) -> tuple[bool, list[str]]:
    blockers = gate_blockers(project)
    return (not blockers), blockers


def mark_ready_flag(project: InvestProject) -> bool:
    ok, blockers = can_push_to_bitrix(project)
    ext = dict(project.external_ids or {})
    ext["ready_for_bitrix"] = ok
    ext["gate_blockers"] = blockers
    ext["completeness_pct"] = compute_completeness(project)
    project.external_ids = ext
    project.save(update_fields=["external_ids", "updated_at"])
    return ok
