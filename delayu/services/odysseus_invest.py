"""Invest → Odysseus context bridge (P3 + investor demo chat)."""
from __future__ import annotations

from decimal import Decimal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse

from delayu.models import SubsystemModule
from delayu.models_odysseus import OdysseusSettings
from delayu.services.access import user_can
from delayu.services.odysseus_settings import ensure_odysseus_settings
from delayu.services.scope import is_platform_admin

SESSION_KEY = "odysseus_invest_context"

# Chat modes (who the AI helps):
# - agency_specialist: AI = специалист Агентства, отвечает на вопросы инвестора по проекту
# - internal_assistant: AI = помощник сотрудника Агентства / руководителя Департамента
ROLE_AGENCY_SPECIALIST = "agency_specialist"
ROLE_INTERNAL_ASSISTANT = "internal_assistant"
DEMO_ROLES = (ROLE_AGENCY_SPECIALIST, ROLE_INTERNAL_ASSISTANT)

# Backward-compatible aliases from the old inverted naming.
_ROLE_ALIASES = {
    "investor_rep": ROLE_AGENCY_SPECIALIST,  # old: AI spoke as investor — now answers investor as agency
    "staff": ROLE_INTERNAL_ASSISTANT,
}

DEMO_STARTERS = {
    ROLE_AGENCY_SPECIALIST: [
        "Какие меры поддержки уже зафиксированы по проекту?",
        "Что входит в пакет документов для передачи в Департамент?",
        "Какова готовность площадки и какие ограничения в карточке?",
        "Есть ли просрочки по дорожной карте?",
        "Какой статус передачи (handoff) Агентство → Департамент?",
        "Кто указан контактным лицом по проекту в карточке?",
    ],
    ROLE_INTERNAL_ASSISTANT: [
        "Собери краткий статус проекта для совещания.",
        "Что не хватает в пакете документов прямо сейчас?",
        "Готовность площадки к брони: какие пробелы?",
        "Какие следующие шаги рекомендовать команде?",
        "Напомни процедуру handoff и текущий статус заявки.",
        "Какие уточнения задать инвестору по отрасли и объёму вложений?",
    ],
}

ROLE_LABELS = {
    ROLE_AGENCY_SPECIALIST: "Специалист Агентства (ответы инвестору)",
    ROLE_INTERNAL_ASSISTANT: "Помощник сотрудника / руководителя",
}

ROLE_HINTS = {
    ROLE_AGENCY_SPECIALIST: "ИИ отвечает как специалист Агентства на вопросы представителя инвестора по выбранному проекту.",
    ROLE_INTERNAL_ASSISTANT: "ИИ помогает сотруднику Агентства или руководителю Департамента: статусы, пакет, следующие шаги.",
}

ROLE_EXAMPLES = {
    ROLE_AGENCY_SPECIALIST: "Пример: «Какие документы нужны в пакете для передачи в Департамент?»",
    ROLE_INTERNAL_ASSISTANT: "Пример: «Краткий статус проекта для совещания у руководителя.»",
}

# Legacy exports (tests / older imports).
ROLE_INVESTOR_REP = ROLE_AGENCY_SPECIALIST
ROLE_STAFF = ROLE_INTERNAL_ASSISTANT

def normalize_demo_role(role: str | None) -> str:
    value = (role or ROLE_AGENCY_SPECIALIST).strip()
    value = _ROLE_ALIASES.get(value, value)
    return value if value in DEMO_ROLES else ROLE_AGENCY_SPECIALIST


def demo_starters_for_role(role: str | None) -> list[str]:
    return list(
        DEMO_STARTERS.get(normalize_demo_role(role), DEMO_STARTERS[ROLE_AGENCY_SPECIALIST])
    )


def user_can_open_invest_odysseus(user, membership, cfg) -> bool:
    """Return whether a user may open Odysseus from the invest subsystem."""
    if not getattr(user, "is_authenticated", False) or not membership or not cfg.enabled:
        return False
    if membership.subsystem_id != cfg.subsystem_id:
        return False
    if membership.subsystem.industry_template != "invest":
        return False

    platform_user = bool(getattr(user, "is_superuser", False) or is_platform_admin(user))
    role_allowed = membership.role.code in cfg.get_role_allowlist()
    if not (platform_user or role_allowed):
        return False

    m87_link = (
        SubsystemModule.objects.filter(subsystem=membership.subsystem, module__code="M87")
        .only("enabled")
        .first()
    )
    if m87_link is None:
        return True
    return bool(m87_link.enabled and (platform_user or user_can(user, "M87", "view")))


def user_can_access_invest_ai_chat(user, membership) -> bool:
    """AI-chat page is available to agency/dept/admin even if Odysseus is offline."""
    if not getattr(user, "is_authenticated", False) or not membership:
        return False
    if membership.subsystem.industry_template != "invest":
        return False
    if getattr(user, "is_superuser", False) or is_platform_admin(user):
        return True
    return membership.role.code in {"invest_agency", "invest_dept", "invest_admin"}


def build_invest_odysseus_context(*, subsystem, project=None, site=None, role: str | None = None) -> dict:
    """Build a compact serializable payload for opening Odysseus from Invest."""
    demo_role = normalize_demo_role(role)
    project = project or _project_from_site(site)
    site = site or _site_from_project(project)
    snapshot = {
        "project": _project_snapshot(project) if project else None,
        "site": _site_snapshot(site) if site else None,
        "automation": _automation_snapshot(subsystem),
    }
    return {
        "kind": "invest_odysseus_context",
        "subsystem_code": subsystem.code,
        "project_id": project.pk if project else None,
        "site_id": site.pk if site else None,
        "demo_role": demo_role,
        "demo_role_label": ROLE_LABELS[demo_role],
        "starters": demo_starters_for_role(demo_role),
        "snapshot": snapshot,
        "prompt_template": _prompt_template(project=project, site=site, role=demo_role),
    }


def prepare_odysseus_open(
    request,
    *,
    membership,
    project=None,
    site=None,
    role: str | None = None,
    starter: str | None = None,
) -> str:
    """Store invest context in session, audit the open event, and return the target URL."""
    cfg = ensure_odysseus_settings(membership.subsystem)
    if not user_can_open_invest_odysseus(request.user, membership, cfg):
        raise PermissionError("Odysseus is unavailable for this user or subsystem.")

    ctx = build_invest_odysseus_context(
        subsystem=membership.subsystem,
        project=project,
        site=site,
        role=role,
    )
    starter_text = (starter or "").strip()
    if starter_text:
        allowed = set(demo_starters_for_role(ctx["demo_role"]))
        if starter_text in allowed:
            ctx["suggested_starter"] = starter_text
            ctx["prompt_template"] = (
                f"{ctx['prompt_template']} Стартовая реплика демо: «{starter_text}»."
            )
    request.session[SESSION_KEY] = ctx
    request.session.modified = True
    _audit_open(request, membership=membership, cfg=cfg, project=project, site=site, role=ctx["demo_role"])

    if cfg.embed_mode == OdysseusSettings.EmbedMode.NEW_TAB:
        return _append_query(
            cfg.base_url,
            {
                "delayu_ctx": "invest",
                "subsystem": membership.subsystem.code,
                "demo_role": ctx["demo_role"],
            },
        )
    return reverse("platform-odysseus")


def get_invest_odysseus_open_url(request, *, membership, project=None, site=None, role: str | None = None) -> str | None:
    """Return the CTA endpoint URL without mutating session or audit state."""
    cfg = ensure_odysseus_settings(membership.subsystem)
    if not user_can_open_invest_odysseus(request.user, membership, cfg):
        return None
    params = {}
    if project:
        params["project"] = project.pk
    if site:
        params["site"] = site.pk
    if role:
        params["role"] = normalize_demo_role(role)
    query = urlencode(params)
    url = reverse("invest-odysseus-open")
    return f"{url}?{query}" if query else url


def _project_snapshot(project) -> dict:
    from delayu.services.invest_package import ensure_package

    overdue_qs = project.roadmap_items.filter(status="overdue")
    overdue_items = list(overdue_qs.values("code", "title", "due_at")[:20])
    overdue_count = overdue_qs.count()

    pkg = ensure_package(project)
    items = list(pkg.items.select_related("document").order_by("id"))
    required = [item for item in items if item.required]
    required_total = len(required)
    required_ready = sum(1 for item in required if item.status == "attached")
    missing = [item for item in required if item.status == "missing"]
    package_items = [
        {
            "code": item.code,
            "title": item.title,
            "required": item.required,
            "status": item.status,
            "status_label": item.get_status_display(),
            "has_file": bool(item.file),
            "document_title": item.document.title if item.document_id else "",
        }
        for item in items
    ]
    support = [
        {"title": row.title, "status": row.status, "status_label": row.get_status_display()}
        for row in project.support_track_items.all().order_by("id")[:20]
    ]
    owner = project.owner
    handoffs = []
    for row in project.handoffs.select_related("requested_by", "decided_by").order_by("-created_at")[:5]:
        handoffs.append(
            {
                "id": row.pk,
                "status": row.status,
                "status_label": row.get_status_display(),
                "requested_by": row.requested_by.get_username() if row.requested_by_id else "",
                "decided_by": row.decided_by.get_username() if row.decided_by_id else "",
                "comment": _compact_text(row.comment),
                "created_at": _json_value(row.created_at),
                "decided_at": _json_value(row.decided_at),
            }
        )
    open_handoff = next((h for h in handoffs if h["status"] == "requested"), None)
    return {
        "code": project.code,
        "name": project.name,
        "stage": project.stage,
        "funnel": project.funnel,
        "organization": str(project.organization),
        "organization_id": project.organization_id,
        "investor_name": _compact_text(project.investor_name),
        "industry": project.industry,
        "description": _compact_text(project.description, limit=500),
        "owner": (
            {
                "id": owner.pk,
                "username": owner.get_username(),
                "name": (owner.get_full_name() or owner.get_username()).strip(),
            }
            if owner
            else None
        ),
        "contact_person": _compact_text(project.contact_person),
        "contact_phone": _compact_text(project.contact_phone),
        "contact_email": _compact_text(project.contact_email),
        "investment_amount": _json_value(project.investment_amount),
        "jobs_count": project.jobs_count,
        "planned_start": _json_value(project.planned_start),
        "planned_end": _json_value(project.planned_end),
        "overdue_roadmap_count": overdue_count,
        "has_overdue": overdue_count > 0,
        "overdue_roadmap": [
            {
                "code": row.get("code"),
                "title": row.get("title"),
                "due_at": _json_value(row.get("due_at")),
            }
            for row in overdue_items
        ],
        "package_ready": f"{required_ready}/{required_total}" if required_total else "0/0",
        "package": {
            "id": pkg.pk,
            "required_ready": required_ready,
            "required_total": required_total,
            "missing_required_count": len(missing),
            "missing_required_titles": [item.title for item in missing],
            "items": package_items,
        },
        "support_measures": support,
        "handoffs": handoffs,
        "open_handoff": open_handoff,
        "handoff_status": open_handoff["status"] if open_handoff else (handoffs[0]["status"] if handoffs else ""),
        "handoff_status_label": (
            open_handoff["status_label"]
            if open_handoff
            else (handoffs[0]["status_label"] if handoffs else "нет заявок")
        ),
    }


def _site_snapshot(site) -> dict:
    return {
        "cadastral_number": site.cadastral_number,
        "name": site.name,
        "status": site.status,
        "organization": str(site.organization),
        "address": _compact_text(site.address),
        "area_ha": _json_value(site.area_ha),
        "right_type": site.right_type,
        "encumbrances": _compact_text(site.encumbrances),
        "zone_info": _compact_text(site.zone_info),
        "completeness_pct": site.completeness_pct,
        "last_smev_at": _json_value(site.last_smev_at),
    }


def _automation_snapshot(subsystem) -> dict:
    try:
        cfg = subsystem.invest_automation_config
    except ObjectDoesNotExist:
        return {"configured": False, "flags": {}}
    return {"configured": True, "flags": cfg.get_flags()}


def _prompt_template(*, project=None, site=None, role: str = ROLE_AGENCY_SPECIALIST) -> str:
    demo_role = normalize_demo_role(role)
    if demo_role == ROLE_AGENCY_SPECIALIST:
        parts = [
            "Ты специалист Агентства инвестиционного развития в чате инвестконтура ДелаЮ.",
            "Собеседник — представитель команды инвестора (или его консультант).",
            "Отвечай на вопросы по проекту, площадке, мерам поддержки, пакету документов, срокам и рискам.",
            "Тон: официально-деловой, понятный, без канцелярской воды. Отвечай по-русски.",
            "Опирайся на JSON-снимок: project.package.items, support_measures, площадку. Не выдумывай факты.",
            "Если данных нет в снимке — скажи об этом прямо и предложи подключить специалиста Агентства.",
            "Никогда не заполняй пробелы догадками.",
        ]
    else:
        parts = [
            "Ты внутренний ИИ-помощник сотрудника Агентства или руководителя Департамента.",
            "Пользователь — не инвестор, а сотрудник контура: ему нужны статусы, пробелы, формулировки и следующие шаги.",
            "Отвечай по-русски, конкретно и по делу.",
            "В JSON-снимке project.package.items — актуальный пакет документов (title, status_label).",
            "Если спрашивают про пакет — перечисли документы и статусы, не говори что пакета нет.",
            "Также используй support_measures, overdue_roadmap и данные площадки.",
            "Не выдумывай факты вне снимка. Если данных нет — предложи подключить профильного специалиста.",
        ]
    if project:
        parts.append("Учти выбранный проект (стадия, пакет, дорожная карта, меры поддержки).")
    if site:
        parts.append("Учти выбранную площадку (готовность карточки, ограничения, кадастр).")
    return " ".join(parts)


def _project_from_site(site):
    if not site:
        return None
    link = site.project_links.select_related("project", "project__organization").first()
    return link.project if link else None


def _site_from_project(project):
    if not project:
        return None
    link = project.site_links.select_related("site", "site__organization").first()
    return link.site if link else None


def _json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _compact_text(value: str, *, limit: int = 240) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _append_query(url: str, params: dict[str, str]) -> str:
    split = urlsplit(url)
    query = dict(parse_qsl(split.query, keep_blank_values=True))
    query.update(params)
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(query), split.fragment))


def _audit_open(request, *, membership, cfg, project=None, site=None, role: str | None = None) -> None:
    from delayu.services.audit import log_action

    model_name = "invest"
    object_id = ""
    if project:
        model_name = "InvestProject"
        object_id = project.pk
    elif site:
        model_name = "InvestSite"
        object_id = site.pk
    log_action(
        request.user,
        membership.subsystem,
        "odysseus.invest.open",
        model_name=model_name,
        object_id=object_id,
        payload={
            "project_id": project.pk if project else None,
            "site_id": site.pk if site else None,
            "demo_role": role,
            "pinned_ref": cfg.pinned_ref,
            "embed_mode": cfg.embed_mode,
        },
        request=request,
    )
