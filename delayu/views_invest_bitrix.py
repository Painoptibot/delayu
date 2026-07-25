"""HTTP webhook Битрикс24 → Delayu (п.1). Без UI."""
from __future__ import annotations

import json

from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from delayu.models import Subsystem
from delayu.services.invest_bitrix import InvestBitrixError, ingest_bitrix_webhook, push_project_to_bitrix
from delayu.services.invest_external_tasks import record_external_answer
from delayu.services.invest_flags import ensure_automation_config
from delayu.models_invest import InvestExternalTask, InvestProject


def _parse_json(request) -> dict:
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _client_ip(request) -> str:
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",", 1)[0].strip()
    return forwarded or request.META.get("REMOTE_ADDR", "")


def _ip_allowed(cfg, request) -> bool:
    allowed = [str(item).strip() for item in (cfg.allowed_ips or []) if str(item).strip()]
    return not allowed or _client_ip(request) in allowed


@method_decorator(csrf_exempt, name="dispatch")
class InvestBitrixWebhookView(View):
    """POST /api/invest/bitrix/webhook/<subsystem_code>/?token=..."""

    def post(self, request, subsystem_code: str, *args, **kwargs):
        subsystem = Subsystem.objects.filter(
            code=subsystem_code, industry_template="invest", status=Subsystem.Status.ACTIVE
        ).first()
        if not subsystem:
            return JsonResponse({"ok": False, "error": "subsystem_not_found"}, status=404)
        cfg = ensure_automation_config(subsystem)
        if not _ip_allowed(cfg, request):
            return JsonResponse({"ok": False, "error": "ip_not_allowed"}, status=403)
        payload = _parse_json(request)
        if not payload:
            payload = request.POST.dict()
        token = request.GET.get("token") or request.headers.get("X-Invest-Token", "")
        try:
            result = ingest_bitrix_webhook(subsystem=subsystem, payload=payload, token=token)
        except InvestBitrixError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        return JsonResponse({"ok": True, **result})


@method_decorator(csrf_exempt, name="dispatch")
class InvestBitrixPushView(View):
    """POST /api/invest/bitrix/push/<project_id>/ — ручной/сервисный outbound."""

    def post(self, request, project_id: int, *args, **kwargs):
        project = InvestProject.objects.select_related("subsystem", "organization").filter(pk=project_id).first()
        if not project:
            return JsonResponse({"ok": False, "error": "project_not_found"}, status=404)
        body = _parse_json(request)
        token = request.GET.get("token") or request.headers.get("X-Invest-Token", "")
        cfg = ensure_automation_config(project.subsystem)
        if cfg.bitrix_webhook_token and token != cfg.bitrix_webhook_token:
            return JsonResponse({"ok": False, "error": "invalid token"}, status=403)
        try:
            result = push_project_to_bitrix(project=project, force=bool(body.get("force")))
        except InvestBitrixError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        return JsonResponse({"ok": True, **result})


@method_decorator(csrf_exempt, name="dispatch")
class InvestExternalTaskAnswerView(View):
    """POST /api/invest/tasks/<id>/answer/ — ответ МО/ТП (п.25)."""

    def post(self, request, task_id: int, *args, **kwargs):
        task = InvestExternalTask.objects.select_related("project", "subsystem").filter(pk=task_id).first()
        if not task:
            return JsonResponse({"ok": False, "error": "task_not_found"}, status=404)
        body = _parse_json(request)
        token = request.GET.get("token") or request.headers.get("X-Invest-Token", "")
        cfg = ensure_automation_config(task.subsystem)
        if cfg.bitrix_webhook_token and token != cfg.bitrix_webhook_token:
            return JsonResponse({"ok": False, "error": "invalid token"}, status=403)
        status = body.get("status") or InvestExternalTask.Status.AGREED
        record_external_answer(task, status=status, payload=body.get("payload") or {})
        return JsonResponse({"ok": True, "task_id": task.pk, "status": task.status})
