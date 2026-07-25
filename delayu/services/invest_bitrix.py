"""Битрикс24 inbound/outbound для инвестконтура (п.1–5, 15–20, 28–29).

По умолчанию sandbox/mock: без живого REST Б24, события пишутся в журнал.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from delayu.models_invest import InvestIntegrationEvent, InvestProject, InvestSite
from delayu.services.invest_dedup import find_duplicate_project, validate_project_requisites
from delayu.services.invest_flags import ensure_automation_config
from delayu.services.invest_gates import can_push_to_bitrix, mark_ready_flag
from delayu.services.invest_journal import finish_event, log_event, retry_or_dead
from delayu.services.invest_pipeline import run_inbound_pipeline

STOP_STAGES = {"TEST", "ARCHIVE", "JUNK", "LOSE"}


class InvestBitrixError(Exception):
    pass


def _map_payload(cfg, payload: dict) -> dict:
    mapping = cfg.field_mapping or {}
    mapped = {}
    unmapped = []
    for src, dst in mapping.items():
        if src in payload and payload[src] not in (None, ""):
            mapped[dst] = payload[src]
        elif src not in payload:
            unmapped.append(src)
    # прямые поля тоже принимаем
    for key in (
        "name",
        "investor_name",
        "industry",
        "investment_amount",
        "jobs_count",
        "contact_person",
        "contact_phone",
        "contact_email",
        "description",
        "organization_code",
        "cadastral_number",
        "bitrix_stage",
        "investor_inn",
    ):
        if key in payload and payload[key] not in (None, ""):
            mapped[key] = payload[key]
    mapped["_unmapped_keys"] = unmapped
    return mapped


def _resolve_org(subsystem, code: str | None):
    if not code:
        return subsystem.organizations.filter(is_active=True).order_by("pk").first()
    org = subsystem.organizations.filter(code=code, is_active=True).first()
    return org or subsystem.organizations.filter(is_active=True).order_by("pk").first()


def _apply_stage(cfg, project: InvestProject, bitrix_stage: str | None):
    if not bitrix_stage:
        return
    pair = (cfg.stage_mapping or {}).get(str(bitrix_stage))
    if not pair:
        return
    funnel, stage = pair
    # воронку меняем только если ещё attraction→attraction или уже support
    if project.funnel == InvestProject.Funnel.SUPPORT and funnel == "attraction":
        return
    if funnel == "support" and project.funnel != InvestProject.Funnel.SUPPORT:
        # handoff только через InvestHandoff — не форсим
        return
    project.stage = stage


def _to_decimal(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", ".").replace(" ", ""))
    except (InvalidOperation, ValueError):
        return None


@transaction.atomic
def ingest_bitrix_webhook(*, subsystem, payload: dict, token: str = "") -> dict:
    """П.1–5: webhook → проект (идемпотентно по bitrix_id)."""
    cfg = ensure_automation_config(subsystem)
    if not cfg.flag("bitrix_inbound"):
        raise InvestBitrixError("bitrix_inbound disabled")
    if cfg.bitrix_webhook_token and token and token != cfg.bitrix_webhook_token:
        raise InvestBitrixError("invalid webhook token")

    bitrix_id = str(payload.get("ID") or payload.get("bitrix_id") or "").strip()
    stage_id = str(payload.get("STAGE_ID") or payload.get("bitrix_stage") or "")
    if stage_id.upper() in STOP_STAGES or payload.get("is_test") or payload.get("is_archive"):
        event = log_event(
            subsystem=subsystem,
            direction=InvestIntegrationEvent.Direction.IN,
            channel=InvestIntegrationEvent.Channel.BITRIX,
            event_type="deal.skip_stoplist",
            external_id=bitrix_id,
            payload=payload,
            status=InvestIntegrationEvent.Status.SKIPPED,
        )
        finish_event(event, status=InvestIntegrationEvent.Status.SKIPPED, response={"reason": "stoplist"})
        return {"skipped": True, "reason": "stoplist", "correlation_id": event.correlation_id}

    event = log_event(
        subsystem=subsystem,
        direction=InvestIntegrationEvent.Direction.IN,
        channel=InvestIntegrationEvent.Channel.BITRIX,
        event_type="deal.upsert",
        external_id=bitrix_id,
        payload=payload,
    )

    mapped = _map_payload(cfg, payload)
    validation_errors = validate_project_requisites({**payload, **mapped})
    dup, dup_by = find_duplicate_project(
        subsystem=subsystem,
        name=str(mapped.get("name") or ""),
        investor_inn=str(mapped.get("investor_inn") or ""),
        bitrix_id=bitrix_id,
    )

    org = _resolve_org(subsystem, mapped.get("organization_code"))
    if not org:
        finish_event(event, status=InvestIntegrationEvent.Status.ERROR, error="no organization")
        raise InvestBitrixError("no organization in subsystem")

    created = False
    if dup:
        project = dup
    else:
        code = f"BX-{bitrix_id}" if bitrix_id else f"BX-AUTO-{timezone.now().strftime('%Y%m%d%H%M%S')}"
        project = InvestProject(
            subsystem=subsystem,
            organization=org,
            code=code,
            name=str(mapped.get("name") or f"Сделка Битрикс {bitrix_id or 'new'}"),
            funnel=InvestProject.Funnel.ATTRACTION,
            stage="lead",
        )
        created = True

    # owner/role hint (п.4)
    owner_hint = payload.get("ASSIGNED_BY_ID") or payload.get("owner_role")
    if str(owner_hint).lower() in {"agency", "invest_agency"}:
        project.external_ids = {**(project.external_ids or {}), "owner_role_hint": "invest_agency"}
    elif str(owner_hint).lower() in {"dept", "invest_dept", "support"}:
        project.external_ids = {**(project.external_ids or {}), "owner_role_hint": "invest_dept"}

    for field in (
        "investor_name",
        "industry",
        "contact_person",
        "contact_phone",
        "contact_email",
        "description",
    ):
        if mapped.get(field):
            setattr(project, field, mapped[field])
    amount = _to_decimal(mapped.get("investment_amount"))
    if amount is not None:
        project.investment_amount = amount
    if mapped.get("jobs_count") not in (None, ""):
        try:
            project.jobs_count = int(mapped["jobs_count"])
        except (TypeError, ValueError):
            pass

    _apply_stage(cfg, project, mapped.get("bitrix_stage") or stage_id)

    ext = dict(project.external_ids or {})
    if bitrix_id:
        ext["bitrix_id"] = bitrix_id
    if mapped.get("investor_inn"):
        ext["investor_inn"] = str(mapped["investor_inn"])
    ext["bitrix_contract_version"] = cfg.contract_version
    ext["last_bitrix_inbound_at"] = timezone.now().isoformat()
    if mapped.get("_unmapped_keys"):
        ext["bitrix_unmapped"] = mapped["_unmapped_keys"]
    if validation_errors:
        ext["validation_errors"] = validation_errors
    if dup_by and created is False:
        ext["dedup_by"] = dup_by
    project.external_ids = ext
    project.organization = org
    project.save()

    event.project = project
    event.save(update_fields=["project"])

    pipeline = run_inbound_pipeline(project=project, cadastral_number=mapped.get("cadastral_number"))
    finish_event(
        event,
        status=InvestIntegrationEvent.Status.DONE,
        response={"created": created, "project_id": project.pk, "pipeline": pipeline, "dedup_by": dup_by},
    )
    return {
        "created": created,
        "project_id": project.pk,
        "code": project.code,
        "dedup_by": dup_by,
        "validation_errors": validation_errors,
        "pipeline": pipeline,
        "correlation_id": event.correlation_id,
    }


def build_passport(project: InvestProject) -> dict:
    """П.13: паспорт проекта для обратной выгрузки."""
    from delayu.services.invest_package import ensure_package

    pkg = ensure_package(project)
    return {
        "code": project.code,
        "name": project.name,
        "investor_name": project.investor_name,
        "industry": project.industry,
        "funnel": project.funnel,
        "stage": project.stage,
        "organization": project.organization.code if project.organization_id else "",
        "investment_amount": str(project.investment_amount) if project.investment_amount is not None else None,
        "jobs_count": project.jobs_count,
        "contacts": {
            "person": project.contact_person,
            "phone": project.contact_phone,
            "email": project.contact_email,
        },
        "support_measures": project.support_measures,
        "package": [
            {"code": i.code, "title": i.title, "status": i.status, "has_file": bool(i.file)}
            for i in pkg.items.all()
        ],
        "sites": [
            {
                "cadastral_number": link.site.cadastral_number,
                "role": link.role,
                "area_ha": str(link.site.area_ha) if link.site.area_ha is not None else None,
                "vri": link.site.vri,
                "right_type": link.site.right_type,
                "address": link.site.address,
            }
            for link in project.site_links.select_related("site")
        ],
        "external_ids": project.external_ids or {},
        "generated_at": timezone.now().isoformat(),
    }


def build_bitrix_outbound_fields(project: InvestProject) -> dict:
    """П.17: структурированные UF-поля для Б24."""
    site = None
    link = project.site_links.select_related("site").order_by("-id").first()
    if link:
        site = link.site
    return {
        "STAGE_ID": project.stage,
        "UF_DELAYU_CODE": project.code,
        "UF_DELAYU_FUNNEL": project.funnel,
        "UF_CADASTRE": site.cadastral_number if site else "",
        "UF_AREA_HA": str(site.area_ha) if site and site.area_ha is not None else "",
        "UF_VRI": site.vri if site else "",
        "UF_RIGHT_TYPE": site.right_type if site else "",
        "UF_ADDRESS": site.address if site else "",
        "UF_ENCUMBRANCES": site.encumbrances if site else "",
        "UF_COORDS": f"{site.latitude},{site.longitude}" if site and site.latitude else "",
        "UF_SUPPORT": project.support_measures,
        "UF_READY": bool((project.external_ids or {}).get("ready_for_bitrix")),
        "UF_COMPLETENESS": (project.external_ids or {}).get("completeness_pct"),
    }


@transaction.atomic
def push_project_to_bitrix(*, project: InvestProject, force: bool = False) -> dict:
    """П.15–20: outbound sync (sandbox пишет в журнал, не дергает живой REST)."""
    subsystem = project.subsystem
    cfg = ensure_automation_config(subsystem)
    if not cfg.flag("bitrix_outbound"):
        raise InvestBitrixError("bitrix_outbound disabled")

    mark_ready_flag(project)
    project.refresh_from_db()
    ok, blockers = can_push_to_bitrix(project)
    if cfg.flag("gate_before_outbound") and not ok and not force:
        event = log_event(
            subsystem=subsystem,
            direction=InvestIntegrationEvent.Direction.OUT,
            channel=InvestIntegrationEvent.Channel.BITRIX,
            event_type="deal.push_blocked",
            external_id=str((project.external_ids or {}).get("bitrix_id") or ""),
            project=project,
            payload={"blockers": blockers},
            status=InvestIntegrationEvent.Status.SKIPPED,
        )
        finish_event(event, status=InvestIntegrationEvent.Status.SKIPPED, response={"blockers": blockers})
        return {"pushed": False, "blockers": blockers, "correlation_id": event.correlation_id}

    passport = build_passport(project)
    fields = build_bitrix_outbound_fields(project)
    comment = (
        f"[Delayu] проверено {timezone.now():%d.%m.%Y %H:%M}; "
        f"полнота {passport['external_ids'].get('completeness_pct')}%; "
        f"источники: СМЭВ/МО/пакет"
    )
    attachments = [
        {"code": item["code"], "title": item["title"], "status": item["status"]}
        for item in passport["package"]
        if item.get("has_file") or item["status"] == "attached"
    ]

    event = log_event(
        subsystem=subsystem,
        direction=InvestIntegrationEvent.Direction.OUT,
        channel=InvestIntegrationEvent.Channel.BITRIX,
        event_type="deal.push",
        external_id=str((project.external_ids or {}).get("bitrix_id") or ""),
        project=project,
        payload={"fields": fields, "passport": passport, "comment": comment, "attachments": attachments},
    )

    # sandbox/mock success
    response = {
        "mode": "sandbox" if cfg.flag("sandbox") else "live_stub",
        "bitrix_id": (project.external_ids or {}).get("bitrix_id"),
        "updated_fields": list(fields.keys()),
        "comment": comment,
        "attachments_count": len(attachments),
        "contract_version": cfg.contract_version,
    }
    try:
        # место для живого REST при smev_live/bitrix live
        if not cfg.flag("sandbox") and cfg.bitrix_api_base:
            response["note"] = "live endpoint configured but REST client not enabled in this build"
        finish_event(event, status=InvestIntegrationEvent.Status.DONE, response=response)
    except Exception as exc:  # pragma: no cover
        retry_or_dead(event, error=str(exc))
        raise

    ext = dict(project.external_ids or {})
    ext["last_bitrix_outbound_at"] = timezone.now().isoformat()
    ext["last_bitrix_outbound_correlation"] = event.correlation_id
    project.external_ids = ext
    project.save(update_fields=["external_ids", "updated_at"])
    return {"pushed": True, "response": response, "correlation_id": event.correlation_id}


def sync_status_to_bitrix(project: InvestProject) -> dict:
    """П.15: узкий sync стадий."""
    return push_project_to_bitrix(project=project, force=False)
