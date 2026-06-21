"""REST: входящие webhook интеграций и Telegram."""
from __future__ import annotations

import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from delayu.models import IntegrationEndpoint, Subsystem
from delayu.services.integration_inbound import (
    process_inbound,
    verify_inbound_access,
    verify_telegram_webhook,
)
from delayu.services.integrations import receive_inbound


def _parse_json(request) -> tuple[dict | None, JsonResponse | None]:
    try:
        body = request.body.decode("utf-8") or "{}"
        data = json.loads(body) if body.strip() else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse({"ok": False, "error": "invalid_json"}, status=400)
    if not isinstance(data, dict):
        return None, JsonResponse({"ok": False, "error": "body_must_be_object"}, status=400)
    return data, None


@csrf_exempt
@require_POST
def api_integration_inbound(request, subsystem_code: str, endpoint_code: str):
    """
    POST /api/v1/integration/inbound/<subsystem>/<endpoint>/
    Заголовок X-Integration-Secret или Bearer API-ключ подсистемы.
    """
    subsystem = get_object_or_404(Subsystem, code=subsystem_code)
    endpoint = get_object_or_404(
        IntegrationEndpoint,
        subsystem=subsystem,
        code=endpoint_code,
        is_active=True,
    )

    auth_err = verify_inbound_access(request, endpoint)
    if auth_err:
        return JsonResponse({"ok": False, "error": auth_err}, status=401)

    payload, err = _parse_json(request)
    if err:
        return err

    try:
        result = process_inbound(endpoint, payload)
    except Exception as exc:
        return JsonResponse({"ok": False, "error": "handler_failed", "detail": str(exc)[:500]}, status=500)

    return JsonResponse(result)


@csrf_exempt
@require_POST
def api_telegram_webhook(request, subsystem_code: str):
    """
    POST /api/v1/telegram/<subsystem>/
    Тело — Update Telegram; заголовок X-Telegram-Bot-Api-Secret-Token при TELEGRAM_WEBHOOK_SECRET.
    """
    subsystem = get_object_or_404(Subsystem, code=subsystem_code)
    auth_err = verify_telegram_webhook(request, subsystem)
    if auth_err:
        return JsonResponse({"ok": False, "error": auth_err}, status=401)

    payload, err = _parse_json(request)
    if err:
        return err

    from delayu.services.integration_inbound import handle_telegram_update

    ep = IntegrationEndpoint.objects.filter(subsystem=subsystem, code="telegram_inbound").first()
    if ep:
        receive_inbound(ep, payload)
    result = handle_telegram_update(subsystem, payload)
    return JsonResponse({"ok": True, **result})
