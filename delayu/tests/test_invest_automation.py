"""Покрытие 30 пунктов автоматизации Битрикс↔Delayu (sandbox)."""
from __future__ import annotations

import io
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from delayu.models import ModuleCatalog, Organization, Role, RoleModulePermission, Subsystem, SubsystemMembership, SubsystemModule
from delayu.models_invest import (
    InvestAutomationConfig,
    InvestExternalTask,
    InvestIntegrationEvent,
    InvestPackageItem,
    InvestProject,
    InvestRoadmapItem,
    InvestSite,
    InvestSmevRequest,
)
from delayu.services.invest_bitrix import (
    build_bitrix_outbound_fields,
    build_passport,
    ingest_bitrix_webhook,
    push_project_to_bitrix,
)
from delayu.services.invest_dedup import find_duplicate_project, inn_is_valid, validate_project_requisites
from delayu.services.invest_escalation import escalate_external_tasks, escalate_overdue_roadmap
from delayu.services.invest_external_tasks import ensure_mo_task, ensure_tp_task, record_external_answer
from delayu.services.invest_flags import ensure_automation_config
from delayu.services.invest_gates import can_push_to_bitrix, compute_completeness, mark_ready_flag
from delayu.services.invest_import import schedule_mo_csv_review
from delayu.services.invest_journal import log_event, requeue_dead_letters, retry_or_dead
from delayu.services.invest_matching import auto_attach_candidates, site_has_active_booking, suggest_sites_for_project
from delayu.services.invest_metrics import collect_metrics, snapshot_metrics
from delayu.services.invest_package import ensure_package, set_item_status
from delayu.services.invest_pipeline import run_inbound_pipeline, run_scheduled_automation
from delayu.services.invest_roles import perm_for_role
from delayu.services.invest_booking import book_site

User = get_user_model()


@pytest.fixture
def auto_ctx(db):
    sub = Subsystem.objects.create(
        code="inv-auto", name="Invest Auto", industry_template="invest", status="active"
    )
    module = ModuleCatalog.objects.create(code="M22", name="Инвестпроекты")
    SubsystemModule.objects.create(subsystem=sub, module=module, enabled=True)
    org = Organization.objects.create(subsystem=sub, code="mo1", name="МО-1")
    role = Role.objects.create(subsystem=sub, code="invest_agency", name="Агентство")
    RoleModulePermission.objects.create(role=role, module=module, **perm_for_role(role.code, "M22"))
    user = User.objects.create_user("auto_agency", password="x", is_superuser=True)
    SubsystemMembership.objects.create(
        user=user, subsystem=sub, organization=org, role=role, is_default=True
    )
    cfg = ensure_automation_config(sub)
    site = InvestSite.objects.create(
        subsystem=sub,
        organization=org,
        cadastral_number="23:00:0000001:1",
        name="Свободная площадка",
        status=InvestSite.Status.ACTUAL,
        completeness_pct=90,
        area_ha="12.5",
        vri="производство",
    )
    return {"sub": sub, "org": org, "user": user, "cfg": cfg, "site": site}


@pytest.mark.django_db
def test_points_01_to_05_bitrix_inbound_dedup_stoplist(auto_ctx):
    sub = auto_ctx["sub"]
    # 1 webhook upsert
    r1 = ingest_bitrix_webhook(
        subsystem=sub,
        payload={
            "ID": "1001",
            "TITLE": "Проект Автотест",
            "UF_INVESTOR": "ООО Тест",
            "UF_INDUSTRY": "АПК",
            "UF_MO_CODE": "mo1",
            "UF_CADASTRE": "23:00:0000001:9",
            "STAGE_ID": "NEW",
            "UF_INN": "7707083893",
            "ASSIGNED_BY_ID": "agency",
        },
        token=auto_ctx["cfg"].bitrix_webhook_token,
    )
    assert r1["created"] is True
    project = InvestProject.objects.get(pk=r1["project_id"])
    assert project.external_ids.get("bitrix_id") == "1001"
    # 2 unmapped journaled in external_ids possibly
    # 3 dedup by bitrix_id
    r2 = ingest_bitrix_webhook(
        subsystem=sub,
        payload={"ID": "1001", "TITLE": "Проект Автотест", "UF_MO_CODE": "mo1"},
        token=auto_ctx["cfg"].bitrix_webhook_token,
    )
    assert r2["created"] is False
    assert InvestProject.objects.filter(subsystem=sub, external_ids__bitrix_id="1001").count() == 1
    # 4 owner hint
    assert project.external_ids.get("owner_role_hint") == "invest_agency"
    # 5 stoplist
    skipped = ingest_bitrix_webhook(
        subsystem=sub,
        payload={"ID": "999", "STAGE_ID": "TEST", "TITLE": "junk"},
        token=auto_ctx["cfg"].bitrix_webhook_token,
    )
    assert skipped["skipped"] is True


@pytest.mark.django_db
def test_points_06_to_14_pipeline_gates_matching_sla(auto_ctx):
    sub, org, site, user = auto_ctx["sub"], auto_ctx["org"], auto_ctx["site"], auto_ctx["user"]
    project = InvestProject.objects.create(
        subsystem=sub,
        organization=org,
        code="P-AUTO",
        name="Пайплайн",
        investor_name="Инвестор",
        industry="АПК",
        funnel=InvestProject.Funnel.ATTRACTION,
        stage="lead",
    )
    # 6 package
    pkg = ensure_package(project)
    assert pkg.items.count() >= 5
    # 7-8 smev via pipeline
    result = run_inbound_pipeline(project=project, cadastral_number="23:00:0000001:9")
    assert result["package_id"]
    assert result["smev"].get("applied") is True
    assert InvestSmevRequest.objects.filter(site__cadastral_number="23:00:0000001:9").count() >= 1
    # 11 candidates
    assert auto_attach_candidates(project)
    assert suggest_sites_for_project(project)
    # 10 booking collision awareness
    book_site(project=project, site=site, user=user)
    assert site_has_active_booking(site) is True
    # 9 completeness / gate
    assert compute_completeness(project) > 0
    ok, blockers = can_push_to_bitrix(project)
    assert "package_incomplete" in blockers or ok is False
    # 12 validation
    assert inn_is_valid("7707083893")
    assert "invalid_inn" in validate_project_requisites({"investor_inn": "123"})
    # 13 passport
    passport = build_passport(project)
    assert passport["code"] == "P-AUTO"
    assert "package" in passport
    # 14 roadmap escalation
    InvestRoadmapItem.objects.create(
        project=project,
        code="land",
        title="Земля",
        due_at=timezone.now() - timedelta(days=1),
        status=InvestRoadmapItem.Status.OPEN,
    )
    assert escalate_overdue_roadmap(subsystem=sub) >= 1


@pytest.mark.django_db
def test_points_15_to_20_outbound_gate_and_fields(auto_ctx):
    sub, org = auto_ctx["sub"], auto_ctx["org"]
    project = InvestProject.objects.create(
        subsystem=sub,
        organization=org,
        code="P-OUT",
        name="Outbound",
        investor_name="ООО",
        industry="Туризм",
        funnel=InvestProject.Funnel.ATTRACTION,
        stage="package_ready",
        external_ids={"bitrix_id": "777"},
    )
    pkg = ensure_package(project)
    for item in pkg.items.filter(required=True):
        set_item_status(item, InvestPackageItem.Status.ATTACHED)
    ensure_mo_task(project)
    # close mo gate
    task = project.external_tasks.get(kind=InvestExternalTask.Kind.MO)
    record_external_answer(task, status=InvestExternalTask.Status.AGREED, payload={"ok": True})
    mark_ready_flag(project)
    project.refresh_from_db()
    ok, blockers = can_push_to_bitrix(project)
    assert ok is True
    # 15-19 push
    pushed = push_project_to_bitrix(project=project)
    assert pushed["pushed"] is True
    fields = build_bitrix_outbound_fields(project)
    assert "UF_DELAYU_CODE" in fields
    assert fields["UF_READY"] is True
    assert InvestIntegrationEvent.objects.filter(event_type="deal.push", project=project).exists()


@pytest.mark.django_db
def test_points_21_to_25_mo_tp_csv_escalation(auto_ctx):
    sub, org = auto_ctx["sub"], auto_ctx["org"]
    project = InvestProject.objects.create(
        subsystem=sub, organization=org, code="P-MO", name="МО", funnel="attraction", stage="lead"
    )
    mo = ensure_mo_task(project)
    tp = ensure_tp_task(project)
    assert mo and tp
    csv_file = SimpleUploadedFile(
        "mo.csv",
        "code,name,stage,investment_amount\nP-NEW,Новый,lead,10\n".encode("utf-8"),
        content_type="text/csv",
    )
    batch = schedule_mo_csv_review(subsystem=sub, organization=org, file_obj=csv_file)
    assert batch.rows.count() >= 1
    mo.due_at = timezone.now() - timedelta(hours=80)
    mo.save(update_fields=["due_at"])
    assert escalate_external_tasks(subsystem=sub) >= 1
    record_external_answer(mo, status=InvestExternalTask.Status.REJECTED, payload={"reason": "нет"})
    project.refresh_from_db()
    assert project.external_ids.get("mo_decision") == "rejected"


@pytest.mark.django_db
def test_points_26_to_30_journal_flags_contract_metrics_runner(auto_ctx, client):
    sub = auto_ctx["sub"]
    cfg = ensure_automation_config(sub)
    assert cfg.contract_version == "v1"
    assert cfg.flag("sandbox") is True
    event = log_event(
        subsystem=sub,
        direction="out",
        channel="bitrix",
        event_type="test.fail",
        payload={},
    )
    retry_or_dead(event, error="boom")
    retry_or_dead(event, error="boom")
    retry_or_dead(event, error="boom")
    event.refresh_from_db()
    assert event.status == InvestIntegrationEvent.Status.DEAD
    assert requeue_dead_letters(subsystem=sub) == 1
    metrics = collect_metrics(subsystem=sub)
    assert "projects_total" in metrics
    run = snapshot_metrics(subsystem=sub)
    assert run.metrics
    scheduled = run_scheduled_automation(subsystem=sub)
    assert "metrics_run_id" in scheduled
    # webhook API
    url = reverse("invest-bitrix-webhook", args=[sub.code])
    resp = client.post(
        f"{url}?token={cfg.bitrix_webhook_token}",
        data='{"ID":"55","TITLE":"API Deal","UF_MO_CODE":"mo1","STAGE_ID":"NEW"}',
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
