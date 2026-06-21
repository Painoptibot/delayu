"""События АИС УЖВ для webhook и каналов уведомлений."""
from __future__ import annotations

from django.urls import reverse

from delayu.models_uzhv import HousingAppeal, HousingQueueCase
from delayu.services.integration_events import emit_integration_event
from delayu.services.notify_dispatch import dispatch_event
from delayu.services.uzhv_appeal_status import status_display as appeal_status_display
from delayu.services.uzhv_case_status import status_display as case_status_display


def _appeal_link(appeal: HousingAppeal) -> str:
    return reverse("uzhv-appeals") + f"?open={appeal.pk}"


def _case_link(case: HousingQueueCase) -> str:
    return reverse("uzhv-cases") + f"?open={case.pk}"


def on_appeal_status_changed(
    appeal: HousingAppeal,
    *,
    old_status: str,
    new_status: str,
    user=None,
    comment: str = "",
) -> None:
    subsystem = appeal.subsystem
    citizen_name = appeal.citizen.full_name if appeal.citizen_id else ""
    payload = {
        "id": appeal.pk,
        "external_id": f"appeal-{appeal.pk}",
        "appeal_number": appeal.appeal_number,
        "from_status": old_status,
        "to_status": new_status,
        "from_status_label": appeal_status_display(old_status),
        "to_status_label": appeal_status_display(new_status),
        "citizen_name": citizen_name,
        "subject": appeal.subject[:500],
        "assignee_id": appeal.assignee_id,
        "comment": comment,
    }
    emit_integration_event(subsystem, "uzhv.appeal.status_changed", payload)

    recipients = []
    if appeal.assignee_id:
        recipients.append(appeal.assignee)
    if user and user not in recipients:
        recipients.append(user)

    ctx = {
        "subject": appeal.subject[:200],
        "appeal_number": appeal.appeal_number,
        "from_status": appeal_status_display(old_status),
        "to_status": appeal_status_display(new_status),
        "citizen": citizen_name,
        "link": _appeal_link(appeal),
        "comment": comment[:200],
    }
    dispatch_event(subsystem, "uzhv_appeal_status_changed", recipients, ctx)


def on_case_status_changed(
    case: HousingQueueCase,
    *,
    old_status: str,
    new_status: str,
    user=None,
    comment: str = "",
) -> None:
    subsystem = case.subsystem
    payload = {
        "id": case.pk,
        "external_id": f"case-{case.pk}",
        "case_number": case.case_number,
        "from_status": old_status,
        "to_status": new_status,
        "from_status_label": case_status_display(old_status),
        "to_status_label": case_status_display(new_status),
        "citizen_name": case.citizen.full_name if case.citizen_id else "",
        "assignee_id": case.assignee_id,
        "comment": comment,
    }
    emit_integration_event(subsystem, "uzhv.case.status_changed", payload)

    recipients = []
    if case.assignee_id:
        recipients.append(case.assignee)
    if user and user not in recipients:
        recipients.append(user)

    ctx = {
        "case": f"{case.case_number} — {case.citizen.full_name if case.citizen_id else ''}".strip(),
        "case_number": case.case_number,
        "from_status": case_status_display(old_status),
        "to_status": case_status_display(new_status),
        "link": _case_link(case),
        "comment": comment[:200],
    }
    dispatch_event(subsystem, "uzhv_case_status_changed", recipients, ctx)
