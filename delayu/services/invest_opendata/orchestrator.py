"""Orchestrate open-data verification runs."""
from __future__ import annotations

import logging
import uuid
from typing import Any

from django.db import transaction
from django.utils import timezone

from delayu.models_invest import (
    InvestInvestor,
    InvestProject,
    InvestSite,
    InvestVerificationRun,
    InvestVerificationSourceResult,
)
from delayu.services.invest_flags import flag_enabled
from delayu.services.invest_opendata.base import CheckContext, SourceResult
from delayu.services.invest_opendata.registry import adapters_for
from delayu.services.invest_opendata.stop_factors import projects_for_context, sync_opendata_stop_factors
from delayu.services.invest_package import ensure_package, set_item_status
from delayu.models_invest import InvestPackageItem

logger = logging.getLogger(__name__)


class InvestOpenDataError(Exception):
    pass


def _use_live(subsystem) -> bool:
    live = flag_enabled(subsystem, "opendata_live", default=False)
    mock = flag_enabled(subsystem, "opendata_mock", default=True)
    return bool(live and not mock)


def _normalize_inn(raw: str) -> str:
    return "".join(ch for ch in (raw or "") if ch.isdigit())


def _ensure_opendata_package_item(project: InvestProject, *, hard_count: int, done: bool) -> None:
    pkg = ensure_package(project)
    item = pkg.items.filter(code="opendata").first()
    if item is None:
        item = InvestPackageItem.objects.create(
            package=pkg,
            code="opendata",
            title="Проверка открытых данных",
            required=True,
            status=InvestPackageItem.Status.MISSING,
        )
    if not done:
        set_item_status(item, InvestPackageItem.Status.PENDING)
    elif hard_count > 0:
        set_item_status(item, InvestPackageItem.Status.PENDING)
    else:
        set_item_status(item, InvestPackageItem.Status.ATTACHED)


def _snapshot_payload(run: InvestVerificationRun, results: list[InvestVerificationSourceResult]) -> dict[str, Any]:
    return {
        "run_id": run.pk,
        "correlation_id": run.correlation_id,
        "status": run.status,
        "summary": run.summary,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "sources": [
            {
                "code": r.source_code,
                "status": r.status,
                "severity": r.severity,
                "title": r.title,
                "external_url": r.external_url,
                "payload": r.payload,
                "error_text": r.error_text,
            }
            for r in results
        ],
    }


def _persist_entity_snapshot(*, investor=None, project=None, site=None, snapshot: dict) -> None:
    if investor is not None:
        extras = dict(investor.extras or {})
        extras["opendata"] = snapshot
        investor.extras = extras
        investor.save(update_fields=["extras", "updated_at"])
    if project is not None:
        ext = dict(project.external_ids or {})
        ext["opendata"] = snapshot
        project.external_ids = ext
        project.save(update_fields=["external_ids", "updated_at"])
    if site is not None:
        ext = dict(site.external_ids or {})
        ext["opendata"] = snapshot
        site.external_ids = ext
        site.save(update_fields=["external_ids", "updated_at"])


def _store_results(run: InvestVerificationRun, results: list[SourceResult]) -> list[InvestVerificationSourceResult]:
    rows = []
    for item in results:
        rows.append(
            InvestVerificationSourceResult(
                run=run,
                source_code=item.source_code,
                status=item.status,
                severity=item.severity,
                title=item.title or item.source_code,
                payload=item.payload or {},
                external_url=item.external_url or "",
                error_text=item.error_text or "",
            )
        )
    InvestVerificationSourceResult.objects.bulk_create(rows)
    return list(run.source_results.all())


def _run(ctx: CheckContext, *, run: InvestVerificationRun) -> InvestVerificationRun:
    run.status = InvestVerificationRun.Status.RUNNING
    run.save(update_fields=["status"])
    adapters = adapters_for(ctx.entity_kind)
    collected: list[SourceResult] = []
    for adapter in adapters:
        try:
            collected.append(adapter.check(ctx))
        except Exception as exc:  # noqa: BLE001
            logger.exception("opendata adapter failed %s", getattr(adapter, "code", "?"))
            collected.append(
                SourceResult(
                    source_code=getattr(adapter, "code", "unknown"),
                    status="error",
                    severity="warn",
                    title=getattr(adapter, "label", "Источник"),
                    error_text=str(exc)[:500],
                )
            )
    stored = _store_results(run, collected)
    hard = [r for r in stored if r.severity == "hard" and r.status == "ok"]
    warn = [r for r in stored if r.severity == "warn"]
    ok_n = sum(1 for r in stored if r.status in ("ok", "empty"))
    run.summary = {
        "hard_count": len(hard),
        "warn_count": len(warn),
        "sources_ok": ok_n,
        "sources_total": len(stored),
        "live": ctx.live,
        "mock": ctx.mock,
    }
    run.status = InvestVerificationRun.Status.DONE
    run.finished_at = timezone.now()
    run.save(update_fields=["summary", "status", "finished_at"])

    hard_items = [(r.source_code, r.title or r.source_code) for r in hard]
    projects = projects_for_context(investor=ctx.investor, project=ctx.project, site=ctx.site)
    sync_opendata_stop_factors(projects=projects, hard_items=hard_items)
    for project in projects:
        _ensure_opendata_package_item(project, hard_count=len(hard), done=True)

    snapshot = _snapshot_payload(run, stored)
    _persist_entity_snapshot(
        investor=ctx.investor,
        project=ctx.project,
        site=ctx.site,
        snapshot=snapshot,
    )
    # Also stamp investor when checking via project
    if ctx.project is not None and ctx.investor is None and ctx.project.investor_entity_id:
        inv = ctx.project.investor_entity
        extras = dict(inv.extras or {})
        extras["opendata"] = snapshot
        inv.extras = extras
        inv.save(update_fields=["extras", "updated_at"])
    return run


@transaction.atomic
def run_investor_verification(investor: InvestInvestor, *, user=None) -> InvestVerificationRun:
    if not investor.inn and not (investor.extras or {}).get("inn"):
        # still allow empty — adapters return empty
        pass
    live = _use_live(investor.subsystem)
    run = InvestVerificationRun.objects.create(
        subsystem=investor.subsystem,
        target_type=InvestVerificationRun.TargetType.INVESTOR,
        investor=investor,
        status=InvestVerificationRun.Status.QUEUED,
        correlation_id=uuid.uuid4().hex,
        triggered_by=user if getattr(user, "is_authenticated", False) else None,
    )
    ctx = CheckContext(
        subsystem=investor.subsystem,
        entity_kind="investor",
        inn=_normalize_inn(investor.inn),
        investor=investor,
        live=live,
        mock=not live,
    )
    return _run(ctx, run=run)


@transaction.atomic
def run_project_verification(project: InvestProject, *, user=None) -> InvestVerificationRun:
    inn = ""
    investor = project.investor_entity
    if investor is not None:
        inn = investor.inn or ""
    if not inn:
        inn = (project.external_ids or {}).get("investor_inn") or ""
    live = _use_live(project.subsystem)
    run = InvestVerificationRun.objects.create(
        subsystem=project.subsystem,
        target_type=InvestVerificationRun.TargetType.PROJECT,
        project=project,
        investor=investor,
        status=InvestVerificationRun.Status.QUEUED,
        correlation_id=uuid.uuid4().hex,
        triggered_by=user if getattr(user, "is_authenticated", False) else None,
    )
    ctx = CheckContext(
        subsystem=project.subsystem,
        entity_kind="project",
        inn=_normalize_inn(inn),
        investor=investor,
        project=project,
        live=live,
        mock=not live,
    )
    return _run(ctx, run=run)


@transaction.atomic
def run_site_verification(site: InvestSite, *, user=None) -> InvestVerificationRun:
    live = _use_live(site.subsystem)
    lat = float(site.latitude) if site.latitude is not None else None
    lon = float(site.longitude) if site.longitude is not None else None
    run = InvestVerificationRun.objects.create(
        subsystem=site.subsystem,
        target_type=InvestVerificationRun.TargetType.SITE,
        site=site,
        status=InvestVerificationRun.Status.QUEUED,
        correlation_id=uuid.uuid4().hex,
        triggered_by=user if getattr(user, "is_authenticated", False) else None,
    )
    ctx = CheckContext(
        subsystem=site.subsystem,
        entity_kind="site",
        cadastral=site.cadastral_number or "",
        latitude=lat,
        longitude=lon,
        site=site,
        live=live,
        mock=not live,
    )
    return _run(ctx, run=run)
