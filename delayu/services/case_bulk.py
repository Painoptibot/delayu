"""#33 — пакетные операции по реестру дел M22."""
from __future__ import annotations

from django.contrib.auth import get_user_model

from delayu.models import BulkOperation
from delayu.services import audit
from delayu.services.operations import run_bulk_operation

User = get_user_model()


def bulk_update_cases(
    *,
    subsystem,
    user,
    ids: list[int],
    action: str,
    status: str = "",
    assignee_id: int | None = None,
    request=None,
) -> BulkOperation:
    filter_params = {"ids": ids}
    payload: dict = {}
    operation = BulkOperation.Operation.STATUS
    if action == "assign":
        operation = BulkOperation.Operation.ASSIGN
        payload["assignee_id"] = assignee_id
    else:
        payload["new_status"] = status
    run = run_bulk_operation(
        subsystem=subsystem,
        user=user,
        operation=operation,
        filter_params=filter_params,
        payload=payload,
    )
    audit.log_action(
        user,
        subsystem,
        "cases.bulk",
        "CaseFile",
        "",
        {
            "operation": operation,
            "count": run.affected_count,
            "ids": ids[:20],
            "payload": payload,
        },
        request,
    )
    return run
