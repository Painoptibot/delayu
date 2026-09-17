"""In-page invest demo chat (roles + project/site context)."""
from __future__ import annotations

import json
from typing import Any

import httpx
from django.conf import settings

from delayu.services.ai_gateway import AiGatewayError, invoke
from delayu.services.odysseus_invest import (
    ROLE_AGENCY_SPECIALIST,
    ROLE_INTERNAL_ASSISTANT,
    SESSION_KEY as CONTEXT_SESSION_KEY,
    normalize_demo_role,
)

CHAT_SESSION_KEY = "invest_ai_chat_messages"
ESCALATION_SESSION_KEY = "invest_ai_chat_escalation"
MAX_HISTORY = 40
ESCALATE_MARKER = "[ESCALATE_SPECIALIST]"
SPECIALIST_SLA_MINUTES = 15

ESCALATE_PHRASES = (
    "не знаю",
    "нет данных",
    "не указан",
    "не указано",
    "не хватает в карточке",
    "недостаточно данных",
    "вне снимка",
    "не могу подтвердить",
    "нужен специалист",
    "подключить специалиста",
    "не буду угадывать",
)

GROUNDING_LABELS = {
    "card": "Ответ по данным системы",
    "system": "Факт системы",
    "offline": "Ответ по данным системы",
    "refuse": "Нужен специалист",
    "escalation": "Эскалация",
    "llm": "ИИ (с ограничениями)",
    "briefing": "Сводка для совещания",
    "specialist": "Специалист в чате",
}

DEMO_SCENARIO = (
    {
        "id": "package",
        "question": "Что входит в пакет документов и что ещё не приложено?",
        "expect": "Пакет из карточки + источники",
    },
    {
        "id": "overdue",
        "question": "Есть ли просрочки по дорожной карте?",
        "expect": "Просрочки ДК из снимка",
    },
    {
        "id": "handoff",
        "question": "Какой сейчас статус передачи в Департамент?",
        "expect": "Статус handoff из карточки",
    },
    {
        "id": "head",
        "question": "Как зовут руководителя департамента инвестиций?",
        "expect": "Отказ без выдуманных имён + специалист",
    },
)

_WEEKDAYS_RU = (
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
)


def get_chat_messages(session) -> list[dict[str, Any]]:
    raw = session.get(CHAT_SESSION_KEY) or []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = _strip_sources_footer((item.get("content") or "").strip())
        if role in {"user", "assistant", "system", "specialist"} and content:
            row = {"role": role, "content": content[:8000]}
            if item.get("grounding"):
                row["grounding"] = item["grounding"]
            if item.get("provenance_label"):
                row["provenance_label"] = item["provenance_label"]
            if item.get("sources"):
                row["sources"] = item["sources"]
            if item.get("at"):
                row["at"] = item["at"]
                row["time"] = _format_message_time(item["at"])
            out.append(row)
    return out[-MAX_HISTORY:]


def _format_message_time(raw: str) -> str:
    value = (raw or "").strip()
    if "T" in value and len(value) >= 16:
        return value[11:16]
    if len(value) >= 5 and value[2] == ":":
        return value[:5]
    return ""


def _strip_sources_footer(content: str) -> str:
    text = content or ""
    marker = "\n\nИсточники:"
    if marker in text:
        return text.split(marker, 1)[0].rstrip()
    return text


def clear_chat_messages(session) -> None:
    session.pop(CHAT_SESSION_KEY, None)
    session.pop(ESCALATION_SESSION_KEY, None)
    session.modified = True


def append_chat_message(
    session,
    *,
    role: str,
    content: str,
    grounding: str = "",
    sources: list[dict[str, str]] | None = None,
) -> None:
    from django.utils import timezone

    messages = get_chat_messages(session)
    row: dict[str, Any] = {
        "role": role,
        "content": (content or "").strip()[:8000],
        "at": timezone.localtime(timezone.now()).isoformat(timespec="seconds"),
    }
    row["time"] = _format_message_time(row["at"])
    if grounding:
        row["grounding"] = grounding
        row["provenance_label"] = GROUNDING_LABELS.get(grounding, grounding)
    if sources:
        row["sources"] = sources[:12]
    messages.append(row)
    session[CHAT_SESSION_KEY] = messages[-MAX_HISTORY:]
    session.modified = True


def llm_configured() -> bool:
    """True when an OpenAI-compatible endpoint is usable (cloud key or local Ollama)."""
    base = (
        getattr(settings, "DELAYU_LLM_BASE_URL", "")
        or getattr(settings, "OPENAI_BASE_URL", "")
        or ""
    ).lower()
    key = getattr(settings, "DELAYU_LLM_API_KEY", "") or getattr(settings, "OPENAI_API_KEY", "")
    if key:
        return True
    return any(h in base for h in ("127.0.0.1", "localhost", "host.docker.internal"))


def llm_model_info() -> dict[str, str]:
    primary = (
        getattr(settings, "DELAYU_LLM_MODEL_DEMO", "")
        or getattr(settings, "DELAYU_LLM_MODEL", "")
        or "gpt-4o-mini"
    )
    fallback = getattr(settings, "DELAYU_LLM_MODEL", "") or primary
    return {"primary": primary, "fallback": fallback}


def llm_runtime_status(*, probe: bool = False) -> dict[str, Any]:
    """Return configured models and optionally which one responds."""
    info = llm_model_info()
    status: dict[str, Any] = {
        **info,
        "configured": llm_configured(),
        "active": "",
        "reachable": False,
        "detail": "",
    }
    if not status["configured"]:
        status["detail"] = "offline"
        return status
    if not probe:
        status["active"] = info["primary"]
        status["detail"] = "configured"
        return status
    try:
        active = _probe_llm_models()
        status["active"] = active or info["fallback"]
        status["reachable"] = bool(active)
        status["detail"] = "ok" if active else "unreachable"
    except Exception as exc:  # noqa: BLE001
        status["active"] = info["fallback"]
        status["reachable"] = False
        status["detail"] = str(exc)[:120]
    return status


def _probe_llm_models() -> str:
    """Try primary then fallback with a tiny completion; return working model id."""
    api_key = (
        getattr(settings, "DELAYU_LLM_API_KEY", "")
        or getattr(settings, "OPENAI_API_KEY", "")
        or "ollama"
    )
    base = (
        getattr(settings, "DELAYU_LLM_BASE_URL", "")
        or getattr(settings, "OPENAI_BASE_URL", "")
        or "https://api.openai.com/v1"
    ).rstrip("/")
    messages = [{"role": "user", "content": "Ответь одним словом: ок"}]
    with httpx.Client(timeout=8.0) as client:
        for model in _llm_models_to_try():
            try:
                resp = client.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"model": model, "messages": messages, "temperature": 0, "max_tokens": 8},
                )
                if resp.status_code < 400:
                    return model
            except Exception:  # noqa: BLE001
                continue
    return ""


def get_escalation(session) -> dict | None:
    raw = session.get(ESCALATION_SESSION_KEY)
    if not isinstance(raw, dict):
        return None
    return _enrich_escalation(raw)


def clear_escalation(session) -> None:
    session.pop(ESCALATION_SESSION_KEY, None)
    session.modified = True


def build_context_card(context: dict | None) -> dict[str, Any]:
    """Compact project/site facts for the chat header."""
    context = context or {}
    snap = context.get("snapshot") or {}
    project = snap.get("project") or {}
    site = snap.get("site") or {}
    package = project.get("package") or {}
    owner = project.get("owner") or {}
    return {
        "demo_role": context.get("demo_role"),
        "demo_role_label": context.get("demo_role_label") or "",
        "project_id": context.get("project_id"),
        "project_code": project.get("code") or "",
        "project_name": project.get("name") or "",
        "stage": project.get("stage") or "",
        "funnel": project.get("funnel") or "",
        "package_ready": project.get("package_ready")
        or (
            f"{package.get('required_ready', 0)}/{package.get('required_total', 0)}"
            if package
            else ""
        ),
        "missing_required_count": package.get("missing_required_count", 0),
        "overdue_roadmap_count": project.get("overdue_roadmap_count", 0),
        "investor_name": project.get("investor_name") or "",
        "owner_name": (owner.get("name") if isinstance(owner, dict) else "") or "",
        "contact_person": project.get("contact_person") or "",
        "handoff_status": project.get("handoff_status") or "",
        "handoff_status_label": project.get("handoff_status_label") or "",
        "site_id": context.get("site_id"),
        "site_name": site.get("name") or "",
        "cadastral_number": site.get("cadastral_number") or "",
        "site_completeness_pct": site.get("completeness_pct"),
        "site_status": site.get("status") or "",
        "facts_only": True,
        "strip": _context_strip_text(project, site, package),
    }


def _context_strip_text(project: dict, site: dict, package: dict) -> str:
    bits = []
    if project.get("code") or project.get("name"):
        bits.append(f"{project.get('code') or ''} {project.get('name') or ''}".strip())
    if project.get("stage"):
        bits.append(f"стадия {project['stage']}")
    ready = project.get("package_ready") or (
        f"{package.get('required_ready', 0)}/{package.get('required_total', 0)}" if package else ""
    )
    if ready:
        bits.append(f"пакет {ready}")
    bits.append(f"просрочки {project.get('overdue_roadmap_count', 0)}")
    if project.get("handoff_status_label"):
        bits.append(f"handoff: {project['handoff_status_label']}")
    if site.get("cadastral_number"):
        pct = site.get("completeness_pct")
        bits.append(
            f"площадка {site['cadastral_number']}"
            + (f" ({pct}%)" if pct is not None else "")
        )
    return " · ".join(bits) if bits else "Контекст не выбран"


def open_specialist_tickets(*, subsystem, limit: int = 20) -> list[dict[str, Any]]:
    from delayu.models_invest import InvestAiChatTicket

    qs = (
        InvestAiChatTicket.objects.filter(
            subsystem=subsystem,
            status__in=[
                InvestAiChatTicket.Status.REQUESTED,
                InvestAiChatTicket.Status.ACCEPTED,
                InvestAiChatTicket.Status.JOINED,
            ],
        )
        .select_related("project", "requested_by", "accepted_by")
        .order_by("-created_at")[:limit]
    )
    rows = []
    for ticket in qs:
        rows.append(
            {
                "id": ticket.pk,
                "status": ticket.status,
                "status_label": ticket.get_status_display(),
                "question": (ticket.question or "")[:240],
                "project_code": ticket.project.code if ticket.project_id else "",
                "project_id": ticket.project_id or "",
                "requested_by": ticket.requested_by.get_username() if ticket.requested_by_id else "",
                "accepted_by": ticket.accepted_by.get_username() if ticket.accepted_by_id else "",
                "created_at": ticket.created_at,
                "sla_minutes": ticket.sla_minutes,
            }
        )
    return rows


def demo_scenario_items() -> list[dict[str, str]]:
    return [dict(item) for item in DEMO_SCENARIO]


def chat_journal(*, subsystem, limit: int = 40) -> list[dict[str, Any]]:
    from delayu.models import AuditLog

    qs = (
        AuditLog.objects.filter(subsystem=subsystem, action__startswith="invest.ai_chat.")
        .select_related("user")
        .order_by("-created_at")[:limit]
    )
    rows: list[dict[str, Any]] = []
    for row in qs:
        payload = row.payload or {}
        rows.append(
            {
                "id": row.pk,
                "at": row.created_at,
                "action": row.action,
                "user": row.user.get_username() if row.user_id else "—",
                "project_id": payload.get("project_id") or row.object_id or "",
                "question": (payload.get("question") or payload.get("user_text") or "")[:240],
                "grounding": payload.get("grounding") or "",
                "offer_specialist": bool(payload.get("offer_specialist")),
                "engine": payload.get("engine") or "",
            }
        )
    return rows


def _enrich_escalation(esc: dict) -> dict:
    from datetime import datetime, timedelta

    from django.utils import timezone

    out = dict(esc)
    timeline = list(out.get("timeline") or [])
    out["timeline"] = timeline
    out["sla_minutes"] = int(out.get("sla_minutes") or SPECIALIST_SLA_MINUTES)
    requested_at = out.get("requested_at")
    if requested_at and out.get("status") in {"requested", "accepted"}:
        try:
            started = datetime.fromisoformat(requested_at)
            if timezone.is_naive(started):
                started = timezone.make_aware(started, timezone.get_current_timezone())
            deadline = started + timedelta(minutes=out["sla_minutes"])
            now = timezone.now()
            remaining = int((deadline - now).total_seconds() // 60)
            out["sla_deadline"] = deadline.isoformat()
            out["sla_remaining_minutes"] = remaining
            out["sla_overdue"] = remaining < 0
        except Exception:  # noqa: BLE001
            out["sla_remaining_minutes"] = None
            out["sla_overdue"] = False
    return out


def _result_payload(
    *,
    reply: str,
    session,
    context: dict,
    engine: str,
    offer_specialist: bool = False,
    grounding: str = "",
    sources: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    esc = get_escalation(session)
    g = grounding or ("refuse" if offer_specialist else engine or "card")
    return {
        "reply": reply,
        "messages": get_chat_messages(session),
        "engine": engine,
        "grounding": g,
        "provenance_label": GROUNDING_LABELS.get(g, g),
        "sources": sources or [],
        "offer_specialist": bool(offer_specialist) and not (esc and esc.get("status") in {"requested", "accepted", "joined"}),
        "escalation": esc,
        "context_card": build_context_card(context),
        "context": {
            "demo_role": context.get("demo_role"),
            "demo_role_label": context.get("demo_role_label"),
            "project_id": context.get("project_id"),
            "site_id": context.get("site_id"),
        },
        "llm": llm_runtime_status(probe=False) if llm_configured() else None,
    }


def _strip_escalate_marker(text: str) -> tuple[str, bool]:
    raw = (text or "").strip()
    flagged = ESCALATE_MARKER in raw
    cleaned = raw.replace(ESCALATE_MARKER, "").strip()
    return cleaned, flagged


def _should_offer_specialist(reply: str, *, marker: bool = False) -> bool:
    if marker:
        return True
    low = (reply or "").lower()
    return any(p in low for p in ESCALATE_PHRASES)


def _format_sources_footer(sources: list[dict[str, str]]) -> str:
    """Legacy helper kept for tests; UI shows sources as chips, not in reply text."""
    if not sources:
        return ""
    lines = [f"• {s.get('label') or s.get('kind')}" for s in sources[:8]]
    return "\n\nИсточники:\n" + "\n".join(lines)


def _infer_sources(context: dict, user_text: str, *, reply: str = "") -> list[dict[str, str]]:
    snap = context.get("snapshot") or {}
    project = snap.get("project") or {}
    site = snap.get("site") or {}
    package = project.get("package") or {}
    q = (user_text or "").lower()
    sources: list[dict[str, str]] = []
    if project and any(k in q for k in ("проект", "статус", "совеща", "кратко", "пакет", "документ", "срок", "дорож", "просроч", "мер", "поддерж")):
        sources.append(
            {
                "kind": "project",
                "label": f"Проект → {project.get('code') or project.get('name') or '#'} (стадия {project.get('stage') or '—'})",
            }
        )
    if package.get("items") and any(k in q for k in ("пакет", "документ")):
        sources.append(
            {
                "kind": "package",
                "label": f"Пакет документов → {package.get('required_ready', 0)}/{package.get('required_total', 0)} обязательных",
            }
        )
        for title in (package.get("missing_required_titles") or [])[:3]:
            sources.append({"kind": "package_item", "label": f"Пакет → документ «{title}»"})
    if project.get("overdue_roadmap") is not None and any(k in q for k in ("срок", "дорож", "просроч")):
        sources.append(
            {
                "kind": "roadmap",
                "label": f"Дорожная карта → просрочек: {project.get('overdue_roadmap_count', 0)}",
            }
        )
    if site and any(k in q for k in ("площад", "кадастр", "ври", "обремен", "брон", "готовност")):
        sources.append(
            {
                "kind": "site",
                "label": f"Площадка → {site.get('cadastral_number') or site.get('name') or '—'} (готовность {site.get('completeness_pct', 'н/д')}%)",
            }
        )
    if project.get("support_measures") and any(k in q for k in ("мер", "поддерж", "льгот")):
        sources.append({"kind": "support", "label": "Проект → меры поддержки"})
    if any(k in q for k in ("handoff", "передач")):
        sources.append(
            {
                "kind": "handoff",
                "label": f"Handoff → {project.get('handoff_status_label') or 'нет заявок'}",
            }
        )
    if project.get("owner") and any(k in q for k in ("ответственн", "куратор", "owner")):
        sources.append({"kind": "owner", "label": "Проект → ответственный (owner)"})
    if "сегодня" in q or "дата" in q or "день недели" in q or "час" in q:
        sources.append({"kind": "system_clock", "label": "Системные часы сервера"})
    if not sources and project and "карточки" not in (reply or "").lower():
        sources.append(
            {
                "kind": "project",
                "label": f"Снимок проекта → {project.get('code') or project.get('name') or '—'}",
            }
        )
    return sources[:8]


def _finish_assistant(
    *,
    request,
    membership,
    context: dict,
    answer: str,
    engine: str,
    grounding: str,
    user_text: str = "",
    sources: list[dict[str, str]] | None = None,
    force_offer: bool | None = None,
    audit_action: str = "invest.ai_chat.message",
) -> dict[str, Any]:
    from delayu.services.audit import log_action

    answer, marker = _strip_escalate_marker(answer)
    if not answer:
        answer = (
            "По доступным данным карточки уверенного ответа нет. "
            "Могу подключить специалиста Агентства к этому чату."
        )
        marker = True
        grounding = "refuse"
    offer = _should_offer_specialist(answer, marker=marker) if force_offer is None else force_offer
    if offer and "специалист" not in answer.lower():
        answer = (
            f"{answer.rstrip()}\n\n"
            "Если нужны точные сведения вне карточки — подключите специалиста Агентства к чату."
        )
        grounding = grounding if grounding in {"refuse", "escalation"} else "refuse"
    src = sources if sources is not None else (_infer_sources(context, user_text, reply=answer) if not offer else [])
    append_chat_message(
        request.session,
        role="assistant",
        content=answer,
        grounding=grounding,
        sources=src,
    )
    log_action(
        request.user,
        membership.subsystem,
        audit_action,
        model_name="InvestProject",
        object_id=context.get("project_id") or "",
        payload={
            "user_text": (user_text or "")[:500],
            "question": (user_text or "")[:500],
            "grounding": grounding,
            "engine": engine,
            "offer_specialist": offer,
            "project_id": context.get("project_id"),
            "site_id": context.get("site_id"),
            "demo_role": context.get("demo_role"),
            "sources": src,
        },
        request=request,
    )
    return _result_payload(
        reply=answer,
        session=request.session,
        context=context,
        engine=engine,
        offer_specialist=offer,
        grounding=grounding,
        sources=src,
    )


def request_specialist(*, request, membership, question: str = "") -> dict[str, Any]:
    """Register a human-specialist join request for the current chat."""
    from django.urls import reverse
    from django.utils import timezone

    from delayu.models import Notification
    from delayu.models_invest import InvestAiChatTicket, InvestProject, InvestProjectComment
    from delayu.services.audit import log_action

    context = request.session.get(CONTEXT_SESSION_KEY) or {}
    messages = get_chat_messages(request.session)
    last_user = ""
    for item in reversed(messages):
        if item["role"] == "user":
            last_user = item["content"]
            break
    question = (question or last_user or "").strip()
    now = timezone.localtime(timezone.now())
    timeline = [
        {
            "at": now.isoformat(timespec="seconds"),
            "status": "requested",
            "label": "Заявка создана",
            "by": request.user.get_username(),
        }
    ]
    project = None
    if context.get("project_id"):
        project = InvestProject.objects.filter(
            pk=context["project_id"], subsystem=membership.subsystem
        ).first()

    ticket = InvestAiChatTicket.objects.create(
        subsystem=membership.subsystem,
        project=project,
        question=question[:2000],
        status=InvestAiChatTicket.Status.REQUESTED,
        demo_role=context.get("demo_role") or "",
        requested_by=request.user,
        sla_minutes=SPECIALIST_SLA_MINUTES,
        timeline=timeline,
        session_key=request.session.session_key or "",
    )

    esc = {
        "status": "requested",
        "ticket_id": ticket.pk,
        "question": question[:2000],
        "requested_at": now.isoformat(),
        "requested_by": request.user.get_username(),
        "demo_role": context.get("demo_role"),
        "project_id": context.get("project_id"),
        "site_id": context.get("site_id"),
        "sla_minutes": SPECIALIST_SLA_MINUTES,
        "timeline": timeline,
    }
    request.session[ESCALATION_SESSION_KEY] = esc
    request.session.modified = True

    if project:
        InvestProjectComment.objects.create(
            project=project,
            author=request.user,
            body=(
                "ИИ-чат: запрошено подключение специалиста.\n"
                f"Заявка #{ticket.pk}\n"
                f"Вопрос: {question[:1500] or '—'}\n"
                f"SLA: {SPECIALIST_SLA_MINUTES} мин."
            ),
        )

    _notify_agency_specialists(
        subsystem=membership.subsystem,
        title=f"ИИ-чат: заявка специалисту #{ticket.pk}",
        body=(question[:300] or "Нужна помощь по проекту")
        + (f" · проект {project.code}" if project else ""),
        link=reverse("invest-ai-chat"),
    )

    log_action(
        request.user,
        membership.subsystem,
        "invest.ai_chat.escalate",
        model_name="InvestAiChatTicket",
        object_id=ticket.pk,
        payload=esc,
        request=request,
    )

    notice = (
        "Заявка специалисту Агентства отправлена. "
        f"Номер заявки #{ticket.pk}. "
        f"Ожидаемый ответ в течение {SPECIALIST_SLA_MINUTES} мин. "
        "Специалист подключится к этому чату и продолжит диалог. "
        f"Тема: «{(question[:180] + '…') if len(question) > 180 else (question or 'уточнение по проекту')}»."
    )
    append_chat_message(
        request.session,
        role="assistant",
        content=notice,
        grounding="escalation",
    )
    return _result_payload(
        reply=notice,
        session=request.session,
        context=context,
        engine="escalation",
        offer_specialist=False,
        grounding="escalation",
    )


def _notify_agency_specialists(*, subsystem, title: str, body: str, link: str) -> int:
    from delayu.models import Notification, SubsystemMembership

    memberships = (
        SubsystemMembership.objects.filter(
            subsystem=subsystem,
            role__code__in=["invest_agency", "invest_dept", "invest_admin"],
        )
        .select_related("user")
        .distinct()
    )
    count = 0
    for m in memberships:
        if not m.user_id:
            continue
        Notification.objects.create(
            user=m.user,
            subsystem=subsystem,
            title=title[:255],
            body=body[:2000],
            link=link[:500],
            level=Notification.Level.WARNING,
        )
        count += 1
    return count


def accept_specialist(*, request, membership) -> dict[str, Any]:
    """Mark escalation accepted (demo: agency/dept staff takes the ticket)."""
    from django.utils import timezone

    from delayu.models_invest import InvestAiChatTicket
    from delayu.services.audit import log_action

    context = request.session.get(CONTEXT_SESSION_KEY) or {}
    esc = get_escalation(request.session)
    if not esc:
        raise ValueError("Нет активной заявки специалисту")
    if esc.get("status") not in {"requested", "accepted"}:
        raise ValueError("Заявка уже закрыта или в другом статусе")
    now = timezone.localtime(timezone.now())
    timeline = list(esc.get("timeline") or [])
    timeline.append(
        {
            "at": now.isoformat(timespec="seconds"),
            "status": "accepted",
            "label": "Специалист принял заявку",
            "by": request.user.get_username(),
        }
    )
    esc.update(
        {
            "status": "accepted",
            "accepted_at": now.isoformat(),
            "accepted_by": request.user.get_username(),
            "timeline": timeline,
        }
    )
    request.session[ESCALATION_SESSION_KEY] = esc
    request.session.modified = True
    ticket = _ticket_from_esc(esc, membership.subsystem)
    if ticket:
        ticket.status = InvestAiChatTicket.Status.ACCEPTED
        ticket.accepted_by = request.user
        ticket.accepted_at = timezone.now()
        ticket.timeline = timeline
        ticket.save(update_fields=["status", "accepted_by", "accepted_at", "timeline", "updated_at"])
        if ticket.project_id:
            from delayu.models_invest import InvestProjectComment

            InvestProjectComment.objects.create(
                project=ticket.project,
                author=request.user,
                body=f"ИИ-чат: специалист принял заявку #{ticket.pk}.",
            )
    notice = (
        f"Специалист {request.user.get_username()} принял заявку"
        + (f" #{ticket.pk}" if ticket else "")
        + ". Можно продолжить диалог в этом чате от лица специалиста."
    )
    append_chat_message(request.session, role="system", content=notice, grounding="escalation")
    log_action(
        request.user,
        membership.subsystem,
        "invest.ai_chat.escalate_accept",
        model_name="InvestAiChatTicket",
        object_id=ticket.pk if ticket else "",
        payload=esc,
        request=request,
    )
    return _result_payload(
        reply=notice,
        session=request.session,
        context=context,
        engine="escalation",
        grounding="escalation",
    )


def specialist_reply(*, request, membership, message: str) -> dict[str, Any]:
    """Post a human-specialist message into the same chat thread."""
    from django.utils import timezone

    from delayu.models_invest import InvestAiChatTicket, InvestProjectComment
    from delayu.services.audit import log_action

    text = (message or "").strip()
    if not text:
        raise ValueError("Пустое сообщение специалиста")
    context = request.session.get(CONTEXT_SESSION_KEY) or {}
    esc = get_escalation(request.session)
    if not esc:
        raise ValueError("Сначала нужна заявка специалисту")
    now = timezone.localtime(timezone.now())
    timeline = list(esc.get("timeline") or [])
    if esc.get("status") != "joined":
        timeline.append(
            {
                "at": now.isoformat(timespec="seconds"),
                "status": "joined",
                "label": "Специалист подключился к чату",
                "by": request.user.get_username(),
            }
        )
    esc.update(
        {
            "status": "joined",
            "joined_at": now.isoformat(),
            "joined_by": request.user.get_username(),
            "timeline": timeline,
        }
    )
    request.session[ESCALATION_SESSION_KEY] = esc
    request.session.modified = True
    ticket = _ticket_from_esc(esc, membership.subsystem)
    if ticket:
        ticket.status = InvestAiChatTicket.Status.JOINED
        ticket.joined_at = timezone.now()
        ticket.timeline = timeline
        if not ticket.accepted_by_id:
            ticket.accepted_by = request.user
            ticket.accepted_at = ticket.accepted_at or timezone.now()
        ticket.save(
            update_fields=["status", "joined_at", "timeline", "accepted_by", "accepted_at", "updated_at"]
        )
        if ticket.project_id:
            InvestProjectComment.objects.create(
                project=ticket.project,
                author=request.user,
                body=f"ИИ-чат / специалист (заявка #{ticket.pk}): {text[:1500]}",
            )
    body = f"Специалист ({request.user.get_username()}): {text}"
    append_chat_message(request.session, role="specialist", content=body, grounding="specialist")
    log_action(
        request.user,
        membership.subsystem,
        "invest.ai_chat.specialist_reply",
        model_name="InvestAiChatTicket",
        object_id=ticket.pk if ticket else "",
        payload={"message": text[:1000], **{k: esc.get(k) for k in ("status", "project_id", "question", "ticket_id")}},
        request=request,
    )
    return _result_payload(
        reply=body,
        session=request.session,
        context=context,
        engine="specialist",
        grounding="specialist",
    )


def _ticket_from_esc(esc: dict | None, subsystem):
    from delayu.models_invest import InvestAiChatTicket

    if not esc:
        return None
    ticket_id = esc.get("ticket_id")
    if ticket_id:
        return InvestAiChatTicket.objects.filter(pk=ticket_id, subsystem=subsystem).first()
    return None


def build_meeting_briefing(*, request, membership) -> dict[str, Any]:
    """One-click 5–7 line status for a department meeting."""
    context = request.session.get(CONTEXT_SESSION_KEY) or {}
    card = build_context_card(context)
    snap = (context.get("snapshot") or {}) if isinstance(context.get("snapshot"), dict) else {}
    project = snap.get("project") or {}
    site = snap.get("site") or {}
    package = project.get("package") or {}
    missing = package.get("missing_required_titles") or []
    overdue = project.get("overdue_roadmap") or []
    lines = [
        "Сводка для совещания (только факты карточки):",
        f"1. Проект: {card.get('project_code') or '—'} «{card.get('project_name') or 'не выбран'}», стадия {card.get('stage') or '—'}.",
        f"2. Пакет документов: {card.get('package_ready') or 'н/д'}; обязательных пробелов: {card.get('missing_required_count', 0)}.",
    ]
    if missing:
        lines.append("3. Не хватает: " + "; ".join(missing[:5]) + ("…" if len(missing) > 5 else "") + ".")
    else:
        lines.append("3. Обязательные позиции пакета в снимке закрыты или пакет не сформирован.")
    if overdue:
        titles = "; ".join((r.get("title") or r.get("code") or "—") for r in overdue[:4])
        lines.append(f"4. Просрочки ДК ({card.get('overdue_roadmap_count', 0)}): {titles}.")
    else:
        lines.append(f"4. Просрочек по дорожной карте: {card.get('overdue_roadmap_count', 0)}.")
    if site:
        lines.append(
            f"5. Площадка {card.get('cadastral_number') or '—'} «{card.get('site_name') or ''}»: "
            f"готовность {card.get('site_completeness_pct', 'н/д')}%, статус {card.get('site_status') or '—'}."
        )
    else:
        lines.append("5. Площадка в контексте не выбрана.")
    investor = card.get("investor_name") or "не указан в карточке"
    owner = card.get("owner_name") or "не указан"
    lines.append(f"6. Инвестор: {investor}; ответственный в карточке: {owner}.")
    lines.append(
        f"7. Handoff: {card.get('handoff_status_label') or 'нет заявок'}; "
        f"контакт: {card.get('contact_person') or 'не указан'}."
    )
    next_step = "закрыть обязательные пробелы пакета"
    if card.get("overdue_roadmap_count"):
        next_step = "разобрать просрочки дорожной карты"
    elif site and (card.get("site_completeness_pct") or 0) < 80:
        next_step = "закрыть пробелы карточки площадки"
    elif card.get("handoff_status") == "requested":
        next_step = "дождаться решения Департамента по handoff"
    lines.append(f"8. Следующий шаг: {next_step}; при вопросах вне карточки — эскалация специалисту.")
    text = "\n".join(lines)
    sources = [
        {"kind": "project", "label": f"Проект → {card.get('project_code') or card.get('project_name') or '—'}"},
        {"kind": "package", "label": f"Пакет → {card.get('package_ready') or 'н/д'}"},
        {"kind": "roadmap", "label": f"Дорожная карта → просрочек {card.get('overdue_roadmap_count', 0)}"},
    ]
    if site:
        sources.append({"kind": "site", "label": f"Площадка → {card.get('cadastral_number') or '—'}"})
    return _finish_assistant(
        request=request,
        membership=membership,
        context=context,
        answer=text,
        engine="briefing",
        grounding="briefing",
        user_text="Сводка для совещания",
        sources=sources,
        force_offer=False,
        audit_action="invest.ai_chat.briefing",
    )


def meeting_briefing_text(context: dict | None) -> str:
    """Plain-text briefing for chat + export (PDF/DOCX)."""
    context = context or {}
    card = build_context_card(context)
    snap = (context.get("snapshot") or {}) if isinstance(context.get("snapshot"), dict) else {}
    project = snap.get("project") or {}
    site = snap.get("site") or {}
    package = project.get("package") or {}
    missing = package.get("missing_required_titles") or []
    overdue = project.get("overdue_roadmap") or []
    lines = [
        "Сводка для совещания (только факты карточки)",
        f"1. Проект: {card.get('project_code') or '—'} «{card.get('project_name') or 'не выбран'}», стадия {card.get('stage') or '—'}.",
        f"2. Пакет: {card.get('package_ready') or 'н/д'}; пробелов: {card.get('missing_required_count', 0)}.",
        "3. Не хватает: " + ("; ".join(missing[:5]) if missing else "обязательные закрыты / пакет пуст") + ".",
        f"4. Просрочки ДК: {card.get('overdue_roadmap_count', 0)}"
        + (
            " ("
            + "; ".join((r.get("title") or r.get("code") or "—") for r in overdue[:4])
            + ")"
            if overdue
            else ""
        )
        + ".",
        (
            f"5. Площадка {card.get('cadastral_number') or '—'} · готовность {card.get('site_completeness_pct', 'н/д')}%."
            if site
            else "5. Площадка не выбрана."
        ),
        f"6. Инвестор: {card.get('investor_name') or '—'}; ответственный: {card.get('owner_name') or '—'}; контакт: {card.get('contact_person') or '—'}.",
        f"7. Handoff: {card.get('handoff_status_label') or 'нет заявок'}.",
    ]
    return "\n".join(lines)


def export_briefing_pdf(context: dict | None) -> bytes:
    from io import BytesIO

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    text = meeting_briefing_text(context)
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    font = "Helvetica"
    for candidate in (
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            pdfmetrics.registerFont(TTFont("BriefFont", candidate))
            font = "BriefFont"
            break
        except Exception:  # noqa: BLE001
            continue
    y = height - 48
    pdf.setFont(font, 14)
    pdf.drawString(48, y, "Сводка ИИ-чата для совещания")
    y -= 28
    pdf.setFont(font, 10)
    for line in text.splitlines():
        if y < 48:
            pdf.showPage()
            y = height - 48
            pdf.setFont(font, 10)
        pdf.drawString(48, y, line[:110])
        y -= 16
    pdf.save()
    return buffer.getvalue()


def export_briefing_docx(context: dict | None) -> bytes:
    from io import BytesIO

    from docx import Document

    text = meeting_briefing_text(context)
    doc = Document()
    doc.add_heading("Сводка ИИ-чата для совещания", level=1)
    for line in text.splitlines():
        doc.add_paragraph(line)
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def reply_to_user_message(
    *,
    request,
    membership,
    user_text: str,
    reset: bool = False,
) -> dict[str, Any]:
    """Append user message, generate assistant reply, persist both in session."""
    text = (user_text or "").strip()
    if not text:
        raise ValueError("Пустое сообщение")
    if reset:
        clear_chat_messages(request.session)
        clear_escalation(request.session)

    context = request.session.get(CONTEXT_SESSION_KEY) or {}
    append_chat_message(request.session, role="user", content=text)

    if _user_asks_specialist(text):
        return request_specialist(request=request, membership=membership, question=text)

    if any(k in text.lower() for k in ("сводк", "совещани", "брифинг")) and any(
        k in text.lower() for k in ("сделай", "дай", "краткий", "кратко", "подготов")
    ):
        # Keep user message; generate briefing without second user append.
        return build_meeting_briefing(request=request, membership=membership)

    factual = _factual_datetime_reply(text)
    if factual:
        return _finish_assistant(
            request=request,
            membership=membership,
            context=context,
            answer=factual,
            engine="system",
            grounding="system",
            user_text=text,
            sources=[{"kind": "system_clock", "label": "Системные часы сервера"}],
            force_offer=False,
        )

    sensitive = _sensitive_topic_reply(context=context, user_text=text)
    if sensitive:
        return _finish_assistant(
            request=request,
            membership=membership,
            context=context,
            answer=sensitive,
            engine="system",
            grounding="refuse",
            user_text=text,
            sources=[],
        )

    person = _person_identity_reply(context=context, user_text=text)
    if person:
        return _finish_assistant(
            request=request,
            membership=membership,
            context=context,
            answer=person,
            engine="system",
            grounding="refuse" if ESCALATE_MARKER in person else "card",
            user_text=text,
            sources=(
                [{"kind": "project", "label": "Проект → поле investor_name"}]
                if "инвестор" in person.lower()
                else []
            ),
        )

    history = get_chat_messages(request.session)
    used_engine = "offline"
    model_used = ""

    def handler() -> str:
        nonlocal used_engine, model_used
        if llm_configured():
            text_out, model_used = _call_openai_compatible(context=context, history=history)
            used_engine = "llm"
            return text_out
        used_engine = "offline"
        return _offline_reply(context=context, user_text=text)

    try:
        answer = invoke(
            membership.subsystem,
            request.user,
            "M22",
            text,
            handler,
            meta={
                "feature": "invest_ai_chat",
                "demo_role": context.get("demo_role"),
                "project_id": context.get("project_id"),
                "site_id": context.get("site_id"),
                "engine": "llm" if llm_configured() else "offline",
                "model": model_used,
            },
        )
    except AiGatewayError:
        answer = _offline_reply(context=context, user_text=text)
        used_engine = "offline"

    answer, marker = _strip_escalate_marker(answer)
    offer = _should_offer_specialist(answer, marker=marker)
    grounding = "refuse" if offer else ("llm" if used_engine == "llm" else "card")
    sources = [] if offer else _infer_sources(context, text, reply=answer)
    return _finish_assistant(
        request=request,
        membership=membership,
        context=context,
        answer=answer + (ESCALATE_MARKER if marker else ""),
        engine=used_engine,
        grounding=grounding,
        user_text=text,
        sources=sources,
        force_offer=offer,
    )


def _user_asks_specialist(text: str) -> bool:
    q = (text or "").lower()
    return any(
        p in q
        for p in (
            "подключи специалиста",
            "подключите специалиста",
            "подключить специалиста",
            "нужен специалист",
            "позовите специалиста",
            "позвать специалиста",
            "живой специалист",
            "оператора",
        )
    )


def _factual_datetime_reply(user_text: str) -> str | None:
    """Return a system-clock answer for date/time questions, else None."""
    from django.utils import timezone

    q = (user_text or "").strip().lower()
    if not q:
        return None
    asks_weekday = "день недели" in q or ("сегодня" in q and "какой день" in q)
    asks_date = asks_weekday or any(k in q for k in ("дата", "число")) or (
        "сегодня" in q and any(k in q for k in ("какая", "какой", "какое", "что", "?"))
    )
    asks_time = any(k in q for k in ("который час", "сколько времени", "текущее время"))
    if not asks_date and not asks_time:
        return None
    now = timezone.localtime(timezone.now())
    weekday = _WEEKDAYS_RU[now.weekday()]
    date_s = now.strftime("%d.%m.%Y")
    if asks_time and not asks_date:
        return f"Сейчас {now.strftime('%H:%M')} ({date_s}, {weekday})."
    if asks_time:
        return f"Сейчас {date_s} {now.strftime('%H:%M')} ({weekday})."
    if asks_weekday and not any(k in q for k in ("дата", "число")):
        return f"Сегодня {weekday}, {date_s}."
    return f"Сегодня {date_s}, {weekday}."


def _asks_person_identity(user_text: str) -> bool:
    q = (user_text or "").strip().lower()
    if not q:
        return False
    role_words = (
        "руководител",
        "директор",
        "начальник",
        "заместител",
        "министр",
        "куратор",
        "ответственн",
        "сотрудник",
        "менеджер",
        "контактн",
    )
    ask_words = (
        "как зовут",
        "как её зовут",
        "как его зовут",
        "фио",
        "фамилия",
        "имя ",
        " кто ",
        "кто ",
        "телефон",
        "email",
        "e-mail",
        "почта",
        "контакт",
    )
    has_role = any(w in q for w in role_words)
    has_ask = any(w in q for w in ask_words) or q.startswith("кто")
    if has_role and has_ask:
        return True
    if "как зовут" in q or "фио" in q:
        return True
    return False


def _person_identity_reply(*, context: dict, user_text: str) -> str | None:
    if not _asks_person_identity(user_text):
        return None
    snap = context.get("snapshot") or {}
    project = (snap.get("project") or {}) if isinstance(snap, dict) else {}
    q = (user_text or "").lower()
    investor = (project.get("investor_name") or "").strip()
    if investor and any(k in q for k in ("инвестор", "заказчик", "инвестора")):
        return f"В карточке проекта указан инвестор: {investor}."
    contact = (project.get("contact_person") or "").strip()
    if contact and any(k in q for k in ("контакт", "контактн", "менеджер проекта")):
        phone = (project.get("contact_phone") or "").strip()
        email = (project.get("contact_email") or "").strip()
        bits = [f"В карточке указано контактное лицо: {contact}."]
        if phone:
            bits.append(f"Телефон: {phone}.")
        if email:
            bits.append(f"E-mail: {email}.")
        return " ".join(bits)
    owner = project.get("owner") or {}
    owner_name = (owner.get("name") if isinstance(owner, dict) else "") or ""
    if owner_name and any(k in q for k in ("ответственн", "владелец", "куратор проекта", "owner")):
        return f"В карточке проекта ответственный (owner): {owner_name}."
    if any(k in q for k in ("руководител", "директор", "начальник", "министр", "департамент")):
        return (
            "ФИО руководителя Департамента в снимке карточки проекта не хранится — "
            "я не буду угадывать имена. Могу подключить специалиста Агентства к этому чату. "
            f"{ESCALATE_MARKER}"
        )
    return (
        "В снимке карточки нет запрошенных персональных данных — "
        "я не буду угадывать. Могу подключить специалиста Агентства к этому чату. "
        f"{ESCALATE_MARKER}"
    )


def _sensitive_topic_reply(*, context: dict, user_text: str) -> str | None:
    """Refuse phones, private contacts, legal promises, amounts outside the card."""
    q = (user_text or "").strip().lower()
    if not q:
        return None
    snap = context.get("snapshot") or {}
    project = (snap.get("project") or {}) if isinstance(snap, dict) else {}

    if any(k in q for k in ("гарантир", "обеща", "юридическ обяз", "подпишем", "гарантия что")):
        return (
            "Юридические обещания и гарантии вне утверждённых документов карточки не даю. "
            "Подключите специалиста Агентства для официальной позиции. "
            f"{ESCALATE_MARKER}"
        )

    if any(k in q for k in ("телефон", "сотовый", "whatsapp", "телеграм", "email", "e-mail", "почта")):
        # Allow only project contact fields from the card.
        if any(k in q for k in ("проект", "карточ", "контактн", "указан")) or project.get("contact_phone") or project.get("contact_email"):
            phone = (project.get("contact_phone") or "").strip()
            email = (project.get("contact_email") or "").strip()
            person = (project.get("contact_person") or "").strip()
            if phone or email:
                bits = []
                if person:
                    bits.append(f"Контактное лицо в карточке: {person}.")
                if phone:
                    bits.append(f"Телефон из карточки: {phone}.")
                if email:
                    bits.append(f"E-mail из карточки: {email}.")
                return " ".join(bits)
        if any(k in q for k in ("руковод", "директор", "начальник", "сотрудник", "личный")):
            return (
                "Контакты руководителей/сотрудников вне полей карточки не раскрываю. "
                f"Могу подключить специалиста. {ESCALATE_MARKER}"
            )

    asks_amount = any(k in q for k in ("сумм", "сколько стоит", "бюджет", "объём вложен", "roi", "маржа", "прибыл"))
    if asks_amount:
        amount = project.get("investment_amount")
        if amount is None or amount == "" or amount == 0:
            return (
                "Точной суммы/ROI вне заполненных полей карточки нет — не выдумываю цифры. "
                f"Подключите специалиста или уточните данные в проекте. {ESCALATE_MARKER}"
            )
        if any(k in q for k in ("roi", "маржа", "прибыл", "закрыт", "nda")):
            return (
                f"В карточке указан объём инвестиций: {amount}. "
                "ROI/маржа и сведения по NDA в снимке отсутствуют — их не раскрываю и не оцениваю. "
                f"{ESCALATE_MARKER}"
            )
    return None


def _system_prompt(context: dict) -> str:
    from django.utils import timezone

    role = normalize_demo_role(context.get("demo_role"))
    base = context.get("prompt_template") or ""
    snapshot = context.get("snapshot") or {}
    project = (snapshot.get("project") or {}) if isinstance(snapshot, dict) else {}
    package = project.get("package") or {}
    now = timezone.localtime(timezone.now())
    bits = [base] if base else []
    bits.append(
        f"Текущие дата и время (факт системы, не выдумывай другие): "
        f"{now.strftime('%d.%m.%Y %H:%M')}, день недели: {_WEEKDAYS_RU[now.weekday()]} "
        f"(timezone {now.tzinfo}). "
        f"Если спрашивают дату или день недели — отвечай только этими фактами."
    )
    bits.append("Режим: только факты из JSON-снимка. Нельзя придумывать «примеры» имён и цифр.")
    if role == ROLE_AGENCY_SPECIALIST:
        bits.append(
            "Отвечай инвестору от лица специалиста Агентства: коротко, по фактам снимка."
        )
    else:
        bits.append(
            "Отвечай сотруднику/руководителю как внутренний помощник: статусы, пробелы, следующие шаги."
        )
    bits.append(
        "Жёсткое правило: не выдумывай факты, имена людей, ФИО, телефоны, должности и «примеры» "
        "(Анна/Сергей и т.п. запрещены, если их нет в JSON). Если ответа нет в снимке/карточке — "
        "честно скажи об этом и предложи подключить специалиста Агентства. В конце такого ответа "
        f"добавь ровно маркер {ESCALATE_MARKER} (служебный, пользователь его не увидит)."
    )
    bits.append(
        "Если в снимке есть project.package.items — это пакет документов. Не утверждай, что пакета нет."
    )
    bits.append("Не выдумывай документы/статусы вне JSON и не выдумывай дату — бери дату только из блока выше.")
    if package.get("items"):
        lines = [
            f"- {it.get('title')}: {it.get('status_label') or it.get('status')}"
            + (" (обязательный)" if it.get("required") else "")
            for it in package["items"]
        ]
        bits.append(
            "Пакет документов проекта "
            f"({package.get('required_ready')}/{package.get('required_total')} обязательных готово):\n"
            + "\n".join(lines)
        )
        if package.get("missing_required_titles"):
            bits.append(
                "Не хватает обязательных: " + "; ".join(package["missing_required_titles"])
            )
    bits.append("Полный JSON-снимок: " + json.dumps(snapshot, ensure_ascii=False)[:12000])
    return "\n".join(bits)


def _llm_models_to_try() -> list[str]:
    info = llm_model_info()
    models = [info["primary"]]
    if info["fallback"] and info["fallback"] not in models:
        models.append(info["fallback"])
    return models


def _call_openai_compatible(*, context: dict, history: list[dict[str, Any]]) -> tuple[str, str]:
    api_key = (
        getattr(settings, "DELAYU_LLM_API_KEY", "")
        or getattr(settings, "OPENAI_API_KEY", "")
        or "ollama"
    )
    base = (
        getattr(settings, "DELAYU_LLM_BASE_URL", "")
        or getattr(settings, "OPENAI_BASE_URL", "")
        or "https://api.openai.com/v1"
    ).rstrip("/")
    messages = [{"role": "system", "content": _system_prompt(context)}]
    for item in history[-20:]:
        role = item.get("role")
        if role == "specialist":
            role = "assistant"
        if role in {"user", "assistant"}:
            messages.append({"role": role, "content": item["content"]})

    last_error: Exception | None = None
    with httpx.Client(timeout=120.0) as client:
        for model in _llm_models_to_try():
            try:
                resp = client.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"model": model, "messages": messages, "temperature": 0.1},
                )
                resp.raise_for_status()
                data = resp.json()
                return (data["choices"][0]["message"]["content"] or "").strip(), model
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue
    if last_error:
        raise last_error
    return "", ""


def _offline_reply(*, context: dict, user_text: str) -> str:
    """Deterministic demo replies grounded in session snapshot."""
    role = normalize_demo_role(context.get("demo_role"))
    snap = context.get("snapshot") or {}
    project = snap.get("project") or {}
    site = snap.get("site") or {}
    q = user_text.lower()

    factual = _factual_datetime_reply(user_text)
    if factual:
        return factual

    project_line = ""
    if project:
        project_line = (
            f"Проект «{project.get('name') or project.get('code') or '—'}» "
            f"(стадия: {project.get('stage') or '—'}, пакет: {project.get('package_ready') or 'н/д'}, "
            f"просрочки ДК: {project.get('overdue_roadmap_count', 0)})."
        )
    site_line = ""
    if site:
        site_line = (
            f"Площадка {site.get('cadastral_number') or '—'} «{site.get('name') or ''}», "
            f"готовность карточки {site.get('completeness_pct', 0)}%, "
            f"статус {site.get('status') or '—'}."
        )

    package = project.get("package") or {}
    items = package.get("items") or []

    def _package_block() -> str:
        if not items:
            return f"Пакет: {project.get('package_ready') or 'н/д'}."
        lines = [
            f"— {it.get('title')}: {it.get('status_label') or it.get('status')}" for it in items
        ]
        missing = package.get("missing_required_titles") or []
        missing_line = (
            "Не хватает обязательных: " + "; ".join(missing) + "."
            if missing
            else "Обязательные позиции пакета закрыты."
        )
        return (
            f"Готовность обязательных: {package.get('required_ready')}/{package.get('required_total')}.\n"
            + "\n".join(lines)
            + f"\n{missing_line}"
        )

    if role == ROLE_AGENCY_SPECIALIST:
        if any(k in q for k in ("мер", "поддерж", "льгот", "субсид")):
            measures = project.get("support_measures") or []
            if measures:
                listed = "; ".join(
                    f"{m.get('title')} ({m.get('status_label') or m.get('status')})" for m in measures
                )
                return (
                    f"По проекту доступны / в работе меры поддержки: {listed}. "
                    f"{project_line} При необходимости уточним отраслевой профиль для подбора дополнительных инструментов."
                )
            return (
                f"Для проекта в снимке меры поддержки пока не зафиксированы отдельным списком. "
                f"{project_line} Можем разобрать налоговые, инфраструктурные и сопровождение после уточнения отрасли и объёма вложений."
            )
        if any(k in q for k in ("документ", "пакет")):
            return (
                "Для передачи в Департамент используется пакет документов проекта:\n"
                f"{_package_block()}\n{project_line}"
            ).strip()
        if any(k in q for k in ("площад", "кадастр", "ври", "обремен", "брон")):
            return (
                f"{site_line or 'Площадка в контексте не выбрана — укажите площадку слева.'} "
                "Перед бронированием закрываем пробелы карточки, обременения и актуальный контур."
            )
        if any(k in q for k in ("срок", "дорож", "просроч")):
            overdue = project.get("overdue_roadmap") or []
            if overdue:
                titles = "; ".join(row.get("title") or row.get("code") or "—" for row in overdue)
                return f"{project_line} Просрочки по дорожной карте: {titles}."
            return f"{project_line or 'Проект не выбран.'} Просрочек по дорожной карте в снимке нет."
        if any(k in q for k in ("привет", "здравствуй", "добрый", "помощь", "помоги")):
            return (
                f"Готов ответить по проекту и площадке. {project_line} {site_line} "
                "Можете спросить про меры поддержки, пакет документов, сроки или риски."
            ).strip()
        return (
            f"В карточке/снимке нет данных для уверенного ответа на этот вопрос. "
            f"{project_line} {site_line} "
            f"Могу подключить специалиста Агентства к чату. {ESCALATE_MARKER}"
        ).strip()

    if any(k in q for k in ("пакет", "документ", "ответ", "инвестор")):
        return (
            "Сводка по пакету для внутренней работы:\n"
            f"{_package_block()}\n{project_line}\n{site_line}"
        ).strip()
    if any(k in q for k in ("статус", "совеща", "кратко", "руковод")):
        return (
            f"Краткий статус для совещания. {project_line or 'Проект не выбран.'} "
            f"{site_line} Пакет: {project.get('package_ready') or 'н/д'}. "
            "Рекомендация: закрыть обязательные пробелы пакета и зафиксировать сроки ДК."
        )
    if any(k in q for k in ("следующ", "шаг", "рекоменд")):
        return (
            "Следующие шаги: закрыть обязательные позиции пакета; "
            f"проверить готовность площадки ({site.get('completeness_pct', 'н/д')}%); "
            "при готовности — handoff Агентство → Департамент; "
            "уточнить у инвестора отрасль и объём вложений при необходимости."
        )
    if any(k in q for k in ("брон", "готовност", "пробел")):
        pct = site.get("completeness_pct")
        return (
            f"{site_line or 'Площадка не выбрана.'} "
            + (f"Готовность карточки {pct}%. " if pct is not None else "")
            + "Проверьте обременения, зоны и актуальный СМЭВ-снимок."
        )
    if any(k in q for k in ("handoff", "передач", "департамент")):
        label = project.get("handoff_status_label") or "нет заявок"
        open_h = project.get("open_handoff")
        detail = ""
        if open_h:
            detail = f" Открытая заявка: {open_h.get('status_label')} (от {open_h.get('requested_by') or '—'})."
        return (
            "Handoff Агентство → Департамент. "
            f"Текущий статус в карточке: {label}.{detail} "
            f"{project_line or 'Выберите проект слева.'}"
        )
    if any(k in q for k in ("вопрос", "уточн", "инвестор")):
        return (
            "Вопросы инвестору на уточнение: отрасль/ОКВЭД; объём инвестиций и срок реализации; "
            "потребность в мерах поддержки; готовность предоставить документы пакета; "
            "предпочитаемая площадка и ограничения по срокам брони."
        )
    if any(k in q for k in ("привет", "здравствуй", "добрый", "помощь", "помоги", "что умеешь")):
        return (
            "Могу помочь со статусом, пакетом, площадкой, handoff и вопросами к инвестору. "
            f"{project_line} {site_line}"
        )
    return (
        f"Недостаточно данных в карточке для уверенного ответа. {project_line} {site_line} "
        f"Предлагаю подключить специалиста Агентства. {ESCALATE_MARKER}"
    )
