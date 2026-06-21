"""История статусов учётных дел УЖВ."""
from __future__ import annotations

from delayu.models_uzhv import HousingCaseStatusHistory, HousingQueueCase


def status_display(code: str) -> str:
    return dict(HousingQueueCase.Status.choices).get(code, code or "—")


def record_case_status_change(
    case: HousingQueueCase,
    *,
    old_status: str,
    new_status: str,
    user=None,
    comment: str = "",
) -> HousingCaseStatusHistory | None:
    if old_status == new_status:
        return None
    entry = HousingCaseStatusHistory.objects.create(
        case=case,
        from_status=old_status or "",
        to_status=new_status,
        changed_by=user,
        comment=comment.strip(),
    )
    from delayu.services.uzhv_integration_events import on_case_status_changed

    on_case_status_changed(
        case,
        old_status=old_status,
        new_status=new_status,
        user=user,
        comment=comment,
    )
    return entry


def build_removal_comment(case: HousingQueueCase) -> str:
    parts = []
    if case.removal_reason:
        parts.append(case.get_removal_reason_display())
    if case.removed_at:
        parts.append(f"дата снятия {case.removed_at:%d.%m.%Y}")
    return "; ".join(parts)
