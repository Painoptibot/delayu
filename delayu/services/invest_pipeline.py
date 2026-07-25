"""Оркестратор входящего пайплайна проверок (п.6–14, 21–23)."""
from __future__ import annotations

from django.contrib.auth import get_user_model

from delayu.models_invest import InvestProject, InvestSite, InvestSmevRequest
from delayu.services.invest_escalation import escalate_external_tasks, escalate_overdue_roadmap
from delayu.services.invest_external_tasks import ensure_mo_task, ensure_tp_task
from delayu.services.invest_flags import flag_enabled
from delayu.services.invest_gates import mark_ready_flag
from delayu.services.invest_matching import auto_attach_candidates
from delayu.services.invest_package import ensure_package
from delayu.services.invest_smev import apply_smev_response, request_smev_fill


User = get_user_model()


def _system_user():
    return User.objects.filter(is_superuser=True).order_by("pk").first()


def ensure_site_from_cadastral(project: InvestProject, cadastral_number: str | None) -> InvestSite | None:
    if not cadastral_number:
        return None
    site, _ = InvestSite.objects.get_or_create(
        subsystem=project.subsystem,
        cadastral_number=str(cadastral_number).strip(),
        defaults={
            "organization": project.organization,
            "name": f"ЗУ {cadastral_number}",
            "status": InvestSite.Status.DRAFT,
            "completeness_pct": 10,
        },
    )
    from delayu.services.invest_matching import link_candidate

    link_candidate(project, site)
    return site


def auto_smev_enrich_site(site: InvestSite, *, user=None) -> dict:
    """П.7–8: автозапросы ЕГРН (+ заглушки ИСОГД/РГИС) и apply ЕГРН."""
    result = {"requests": [], "applied": False}
    if not flag_enabled(site.subsystem, "auto_smev"):
        return result
    actor = user or _system_user()
    for service in (
        InvestSmevRequest.Service.EGRN,
        InvestSmevRequest.Service.ISOGD,
        InvestSmevRequest.Service.RGIS,
    ):
        req = request_smev_fill(site=site, user=actor, service=service)
        result["requests"].append({"id": req.pk, "service": req.service, "status": req.status})
        if service == InvestSmevRequest.Service.EGRN and req.status == InvestSmevRequest.Status.DONE:
            apply_smev_response(request=req, user=actor)
            result["applied"] = True
    return result


def run_inbound_pipeline(*, project: InvestProject, cadastral_number: str | None = None) -> dict:
    """Полный конвейер после появления/обновления объекта из Б24."""
    out = {
        "package_id": None,
        "smev": {},
        "candidates": [],
        "mo_task_id": None,
        "tp_task_id": None,
        "ready": False,
    }
    if flag_enabled(project.subsystem, "auto_package"):
        pkg = ensure_package(project)
        out["package_id"] = pkg.pk

    site = ensure_site_from_cadastral(project, cadastral_number)
    if site and flag_enabled(project.subsystem, "auto_smev"):
        out["smev"] = auto_smev_enrich_site(site)

    if flag_enabled(project.subsystem, "auto_site_match"):
        out["candidates"] = auto_attach_candidates(project)

    mo = ensure_mo_task(project)
    tp = ensure_tp_task(project)
    out["mo_task_id"] = mo.pk if mo else None
    out["tp_task_id"] = tp.pk if tp else None
    out["ready"] = mark_ready_flag(project)
    return out


def run_scheduled_automation(*, subsystem) -> dict:
    """Периодический runner: SLA, эскалации, метрики, CSV-ready hook (п.14,22,24,30)."""
    from delayu.services.invest_metrics import snapshot_metrics

    roadmap = escalate_overdue_roadmap(subsystem=subsystem)
    tasks = escalate_external_tasks(subsystem=subsystem)
    run = snapshot_metrics(subsystem=subsystem, notes="scheduled")
    return {
        "roadmap_escalations": roadmap,
        "task_escalations": tasks,
        "metrics_run_id": run.pk,
        "metrics": run.metrics,
        "mo_csv_hint": "use invest import UI / parse_mo_file for scheduled CSV apply",
    }
