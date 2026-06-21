"""REST API v1 — M43."""
import json

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods

from delayu.models import CaseFile, IntegrationMessage, ModuleCatalog, TaskItem
from delayu.services.api_gateway import api_access
from delayu.services.object_registry import global_search
from delayu.services.openapi_contract import build_openapi_spec
from delayu.services.ai import get_or_create_policy, serialize_ai_policy, update_ai_policy


def _platform_version() -> str:
    return getattr(settings, "DELAYU_PLATFORM_VERSION", "2.2.0")


@require_GET
@api_access(public=True)
def api_health(request):
    db_ok = True
    migration_ok = True
    index_ok = True
    try:
        connection.ensure_connection()
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception:
        db_ok = False
    try:
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        migration_ok = len(plan) == 0
    except Exception:
        migration_ok = False
    try:
        from delayu.models import SearchIndexEntry

        index_ok = SearchIndexEntry.objects.exists()
    except Exception:
        index_ok = False
    checks = {
        "database": db_ok,
        "migrations": migration_ok,
        "search_index": index_ok,
    }
    status = "ok" if db_ok and migration_ok else "degraded"
    payload = {
        "status": status,
        "platform": "ДелаЮ",
        "version": _platform_version(),
        "checks": checks,
    }
    if getattr(request, "api_key", None):
        payload["subsystem"] = request.api_subsystem.code
    return JsonResponse(payload)


@require_GET
@api_access(public=True)
def api_openapi_contract(request):
    return JsonResponse(build_openapi_spec())


@require_GET
@api_access()
def api_cases(request):
    from delayu.services.org_scope import apply_organization_scope

    sub = request.api_subsystem
    user = request.api_user or getattr(request, "user", None)
    qs = apply_organization_scope(user, sub, CaseFile.objects.filter(subsystem=sub, is_archived=False))
    data = list(qs.values("id", "number", "title", "status", "due_date", "organization_id")[:100])
    return JsonResponse({"results": data, "count": len(data)})


@require_GET
@api_access()
def api_modules(request):
    mods = list(ModuleCatalog.objects.filter(is_active=True).values("code", "name", "group"))
    return JsonResponse({"results": mods})


@require_GET
@api_access()
def api_tasks(request):
    sub = request.api_subsystem
    user = request.api_user or request.user
    data = list(
        TaskItem.objects.filter(subsystem=sub, assignee=user).values(
            "id", "title", "kanban_column", "due_date"
        )[:100]
    )
    return JsonResponse({"results": data})


@require_GET
@api_access()
def api_search(request):
    q = request.GET.get("q", "").strip()
    user = request.api_user or getattr(request, "user", None)
    results = global_search(request.api_subsystem, q, user=user)
    return JsonResponse({"query": q, "results": results, "count": len(results)})


@require_GET
@api_access(module_code="M09")
def api_calendar_events(request):
    """Синхронизация календаря ↔ задачи."""
    sub = request.api_subsystem
    qs = TaskItem.objects.filter(subsystem=sub).exclude(due_date__isnull=True)
    events = []
    for t in qs[:200]:
        color = "#696cff"
        if t.priority == 1:
            color = "#ff4d49"
        elif t.priority == 2:
            color = "#ff9f43"
        events.append(
            {
                "id": str(t.pk),
                "title": t.title,
                "start": t.due_date.isoformat(),
                "allDay": True,
                "backgroundColor": color,
                "borderColor": color,
                "extendedProps": {"taskId": t.pk, "priority": t.priority},
            }
        )
    return JsonResponse({"events": events})


def _message_json(msg: IntegrationMessage) -> dict:
    return {
        "id": msg.pk,
        "endpoint": msg.endpoint.code,
        "direction": msg.direction,
        "status": msg.status,
        "retry_count": msg.retry_count,
        "error_text": msg.error_text,
        "external_id": msg.external_id,
        "created_at": msg.created_at.isoformat(),
    }


@require_GET
@api_access(module_code="M42")
def api_integration_messages(request):
    from delayu.services.integrations import filter_messages, queue_metrics

    sub = request.api_subsystem
    params = {
        "status": request.GET.get("status", ""),
        "endpoint": request.GET.get("endpoint", ""),
        "direction": request.GET.get("direction", ""),
    }
    qs = filter_messages(sub, params)[:100]
    return JsonResponse(
        {
            "results": [_message_json(m) for m in qs],
            "count": len(qs),
            "metrics": queue_metrics(sub),
        }
    )


@require_http_methods(["POST"])
@api_access(module_code="M42")
def api_integration_message_retry(request, pk):
    from delayu.services.integrations import retry_message

    sub = request.api_subsystem
    msg = IntegrationMessage.objects.select_related("endpoint").filter(
        pk=pk, endpoint__subsystem=sub
    ).first()
    if not msg:
        return JsonResponse({"detail": "not_found"}, status=404)
    retry_message(msg)
    msg.refresh_from_db()
    return JsonResponse({"ok": True, "message": _message_json(msg)})


@require_http_methods(["POST"])
@api_access(module_code="M42")
def api_integration_message_dead_letter(request, pk):
    from delayu.services.integrations import move_to_dead_letter

    sub = request.api_subsystem
    msg = IntegrationMessage.objects.select_related("endpoint").filter(
        pk=pk, endpoint__subsystem=sub
    ).first()
    if not msg:
        return JsonResponse({"detail": "not_found"}, status=404)
    move_to_dead_letter(msg, reason="API dead letter")
    msg.refresh_from_db()
    return JsonResponse({"ok": True, "message": _message_json(msg)})


@require_http_methods(["POST"])
@api_access(module_code="M42")
def api_integration_queue_process(request):
    from delayu.services.integrations import process_pending_queue

    sub = request.api_subsystem
    limit = int(request.POST.get("limit") or request.GET.get("limit") or 20)
    result = process_pending_queue(sub, limit=limit)
    return JsonResponse({"ok": True, **result})


@require_GET
@api_access(module_code="M78")
def api_notification_delivery(request):
    from delayu.services.mail_delivery import delivery_metrics, filter_delivery_logs, serialize_log

    sub = request.api_subsystem
    params = {
        "success": request.GET.get("success", ""),
        "direction": request.GET.get("direction", ""),
        "event_code": request.GET.get("event_code", ""),
        "q": request.GET.get("q", ""),
    }
    qs = filter_delivery_logs(sub, params)[:100]
    return JsonResponse(
        {
            "results": [serialize_log(x) for x in qs],
            "count": len(qs),
            "metrics": delivery_metrics(sub),
        }
    )


@require_http_methods(["GET", "PATCH"])
@api_access(module_code="M66")
def api_ai_policy(request):
    """#41 — GET/PATCH политики ИИ подсистемы."""
    sub = request.api_subsystem
    policy = get_or_create_policy(sub)
    if request.method == "GET":
        return JsonResponse(serialize_ai_policy(policy))
    try:
        payload = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"detail": "invalid_json"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"detail": "invalid_body"}, status=400)
    data = update_ai_policy(policy, payload)
    return JsonResponse(data)
