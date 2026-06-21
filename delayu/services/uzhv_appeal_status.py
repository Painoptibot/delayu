"""История статусов обращений граждан УЖВ."""
from __future__ import annotations

from delayu.models_uzhv import HousingAppeal, HousingAppealStatusHistory


def status_display(code: str) -> str:
    return dict(HousingAppeal.Status.choices).get(code, code or "—")


def record_appeal_status_change(
    appeal: HousingAppeal,
    *,
    old_status: str,
    new_status: str,
    user=None,
    comment: str = "",
) -> HousingAppealStatusHistory | None:
    if old_status == new_status:
        return None
    entry = HousingAppealStatusHistory.objects.create(
        appeal=appeal,
        from_status=old_status or "",
        to_status=new_status,
        changed_by=user,
        comment=comment.strip(),
    )
    from delayu.services.uzhv_integration_events import on_appeal_status_changed

    on_appeal_status_changed(
        appeal,
        old_status=old_status,
        new_status=new_status,
        user=user,
        comment=comment,
    )
    return entry
