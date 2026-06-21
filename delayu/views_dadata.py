"""Прокси подсказок DaData (ключ не уходит в браузер)."""
from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from delayu.services import dadata as dadata_service


@login_required
@require_GET
def dadata_status(request):
    return JsonResponse(
        {
            "configured": dadata_service.is_configured(),
            "types": list(dadata_service.SUGGEST_TYPES.keys()),
        }
    )


@login_required
@require_POST
def dadata_suggest(request):
    try:
        body = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "invalid_json"}, status=400)

    suggest_type = (body.get("type") or "").strip()
    query = (body.get("query") or "").strip()
    if not suggest_type:
        return JsonResponse({"error": "type_required"}, status=400)
    if suggest_type not in dadata_service.SUGGEST_TYPES:
        return JsonResponse({"error": "unknown_type"}, status=400)

    try:
        count = int(body.get("count", 10))
    except (TypeError, ValueError):
        count = 10

    extra = body.get("extra")
    if extra is not None and not isinstance(extra, dict):
        return JsonResponse({"error": "extra_must_be_object"}, status=400)

    if len(query) < 1:
        return JsonResponse({"suggestions": [], "configured": dadata_service.is_configured()})

    result = dadata_service.suggest(suggest_type, query, count=count, extra=extra or None)
    return JsonResponse(result)
