"""Invest → Odysseus context bridge (P3)."""
from __future__ import annotations

from decimal import Decimal
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse

from delayu.models import SubsystemModule
from delayu.models_odysseus import OdysseusSettings
from delayu.services.access import user_can
from delayu.services.odysseus_settings import ensure_odysseus_settings
from delayu.services.scope import is_platform_admin

SESSION_KEY = "odysseus_invest_context"


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


def build_invest_odysseus_context(*, subsystem, project=None, site=None) -> dict:
    """Build a compact serializable payload for opening Odysseus from Invest."""
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
        "snapshot": snapshot,
        "prompt_template": _prompt_template(project=project, site=site),
    }


def prepare_odysseus_open(request, *, membership, project=None, site=None) -> str:
    """Store invest context in session, audit the open event, and return the target URL."""
    cfg = ensure_odysseus_settings(membership.subsystem)
    if not user_can_open_invest_odysseus(request.user, membership, cfg):
        raise PermissionError("Odysseus is unavailable for this user or subsystem.")

    ctx = build_invest_odysseus_context(
        subsystem=membership.subsystem,
        project=project,
        site=site,
    )
    request.session[SESSION_KEY] = ctx
    request.session.modified = True
    _audit_open(request, membership=membership, cfg=cfg, project=project, site=site)

    if cfg.embed_mode == OdysseusSettings.EmbedMode.NEW_TAB:
        return _append_query(cfg.base_url, {"delayu_ctx": "invest", "subsystem": membership.subsystem.code})
    return reverse("platform-odysseus")


def get_invest_odysseus_open_url(request, *, membership, project=None, site=None) -> str | None:
    """Return the CTA endpoint URL without mutating session or audit state."""
    cfg = ensure_odysseus_settings(membership.subsystem)
    if not user_can_open_invest_odysseus(request.user, membership, cfg):
        return None
    params = {}
    if project:
        params["project"] = project.pk
    if site:
        params["site"] = site.pk
    query = urlencode(params)
    url = reverse("invest-odysseus-open")
    return f"{url}?{query}" if query else url


def _project_snapshot(project) -> dict:
    overdue_count = project.roadmap_items.filter(status="overdue").count()
    active_package = project.packages.filter(is_active=True).prefetch_related("items").first()
    required_total = required_ready = 0
    if active_package:
        required = [item for item in active_package.items.all() if item.required]
        required_total = len(required)
        required_ready = sum(1 for item in required if item.status == "attached")
    return {
        "code": project.code,
        "name": project.name,
        "stage": project.stage,
        "funnel": project.funnel,
        "organization": str(project.organization),
        "investor_name": _compact_text(project.investor_name),
        "industry": project.industry,
        "investment_amount": _json_value(project.investment_amount),
        "jobs_count": project.jobs_count,
        "overdue_roadmap_count": overdue_count,
        "has_overdue": overdue_count > 0,
        "package_ready": f"{required_ready}/{required_total}" if required_total else "",
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


def _prompt_template(*, project=None, site=None) -> str:
    parts = ["Ты Odysseus для инвестконтура ДелаЮ."]
    if project:
        parts.append("Проанализируй проект, риски дорожной карты, пакет документов и следующие шаги.")
    if site:
        parts.append("Оцени площадку: готовность карточки, ограничения, СМЭВ/ЕГРН и пригодность для проекта.")
    parts.append("Используй переданный JSON-контекст как краткий снимок, не запрашивай лишние ПДн.")
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


def _audit_open(request, *, membership, cfg, project=None, site=None) -> None:
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
            "pinned_ref": cfg.pinned_ref,
            "embed_mode": cfg.embed_mode,
        },
        request=request,
    )
