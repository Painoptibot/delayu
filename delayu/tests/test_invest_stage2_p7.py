from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from delayu.models import ModuleCatalog, Organization, Role, RoleModulePermission, Subsystem, SubsystemMembership, SubsystemModule
from delayu.models_invest import InvestAutomationConfig, InvestIntegrationEvent, InvestPackageItem, InvestProject, InvestSite, InvestSmevRequest
from delayu.services.invest_bitrix import ingest_bitrix_webhook, push_project_to_bitrix
from delayu.services.invest_external_tasks import ensure_mo_task, record_external_answer
from delayu.services.invest_flags import ensure_automation_config
from delayu.services.invest_gates import can_push_to_bitrix
from delayu.services.invest_package import ensure_package, set_item_status
from delayu.services.invest_roles import perm_for_role
from delayu.services.invest_smev import request_smev_fill

User = get_user_model()


@pytest.fixture
def p7_ctx(db):
    sub = Subsystem.objects.create(
        code="inv-p7", name="Invest P7", industry_template="invest", status=Subsystem.Status.ACTIVE
    )
    module = ModuleCatalog.objects.create(code="M22", name="Инвестпроекты")
    SubsystemModule.objects.create(subsystem=sub, module=module, enabled=True)
    org = Organization.objects.create(subsystem=sub, code="mo1", name="МО-1")
    role = Role.objects.create(subsystem=sub, code="invest_admin", name="Admin")
    RoleModulePermission.objects.create(role=role, module=module, **perm_for_role(role.code, "M22"))
    user = User.objects.create_user("p7-admin", password="x", is_superuser=True)
    SubsystemMembership.objects.create(user=user, subsystem=sub, organization=org, role=role, is_default=True)
    cfg = ensure_automation_config(sub)
    return {"sub": sub, "org": org, "role": role, "user": user, "cfg": cfg}


def _ready_project(ctx, *, code="P7-READY"):
    project = InvestProject.objects.create(
        subsystem=ctx["sub"],
        organization=ctx["org"],
        code=code,
        name="Ready",
        investor_name="ООО Готово",
        industry="АПК",
        funnel=InvestProject.Funnel.ATTRACTION,
        stage="package_ready",
        contact_person="Иван",
        contact_phone="+7",
        description="Описание",
        investment_amount="10.00",
        external_ids={"bitrix_id": "777"},
    )
    package = ensure_package(project)
    for item in package.items.filter(required=True):
        set_item_status(item, InvestPackageItem.Status.ATTACHED)
    task = ensure_mo_task(project)
    record_external_answer(task, status="agreed", payload={"ok": True})
    ok, blockers = can_push_to_bitrix(project)
    assert ok, blockers
    return project


@pytest.mark.django_db
def test_bitrix_live_push_posts_to_configured_base(p7_ctx):
    cfg = p7_ctx["cfg"]
    cfg.flags = {**cfg.get_flags(), "sandbox": False}
    cfg.bitrix_api_base = "https://bitrix.example/rest/deal.update"
    cfg.save(update_fields=["flags", "bitrix_api_base", "updated_at"])
    project = _ready_project(p7_ctx)

    with patch("delayu.services.invest_bitrix.httpx.Client") as client_cls:
        response = client_cls.return_value.__enter__.return_value.post.return_value
        response.json.return_value = {"result": True, "ID": "777"}
        response.text = '{"result": true}'
        response.raise_for_status.return_value = None

        result = push_project_to_bitrix(project=project)

    assert result["pushed"] is True
    assert result["response"]["mode"] == "live"
    client_cls.return_value.__enter__.return_value.post.assert_called_once()
    args, kwargs = client_cls.return_value.__enter__.return_value.post.call_args
    assert args == ("https://bitrix.example/rest/deal.update",)
    assert kwargs["json"]["fields"]["UF_DELAYU_CODE"] == project.code


@pytest.mark.django_db
def test_webhook_rejects_unallowed_ip(client, p7_ctx):
    cfg = p7_ctx["cfg"]
    cfg.allowed_ips = ["10.0.0.7"]
    cfg.save(update_fields=["allowed_ips", "updated_at"])

    resp = client.post(
        f"{reverse('invest-bitrix-webhook', args=[p7_ctx['sub'].code])}?token={cfg.bitrix_webhook_token}",
        data='{"ID":"ip-1","TITLE":"Blocked","UF_MO_CODE":"mo1"}',
        content_type="application/json",
        REMOTE_ADDR="10.0.0.8",
    )

    assert resp.status_code == 403
    assert resp.json()["error"] == "ip_not_allowed"


@pytest.mark.django_db
def test_smev_live_stub_creates_pending_request(p7_ctx):
    cfg = p7_ctx["cfg"]
    cfg.flags = {**cfg.get_flags(), "smev_mock": False, "smev_live": True}
    cfg.save(update_fields=["flags", "updated_at"])
    site = InvestSite.objects.create(
        subsystem=p7_ctx["sub"],
        organization=p7_ctx["org"],
        cadastral_number="23:00:0000001:77",
        name="Live site",
    )

    req = request_smev_fill(site=site, user=p7_ctx["user"], service=InvestSmevRequest.Service.EGRN)

    assert req.is_mock is False
    assert req.status == InvestSmevRequest.Status.LIVE_PENDING
    assert "live" in req.response_payload["note"]


@pytest.mark.django_db
def test_stage_conflict_can_accept_bitrix(client, p7_ctx):
    project = InvestProject.objects.create(
        subsystem=p7_ctx["sub"],
        organization=p7_ctx["org"],
        code="BX-42",
        name="Conflict",
        stage="lead",
        external_ids={"bitrix_id": "42"},
    )
    ingest_bitrix_webhook(
        subsystem=p7_ctx["sub"],
        payload={"ID": "42", "TITLE": "Conflict", "UF_MO_CODE": "mo1", "STAGE_ID": "PACKAGE"},
        token=p7_ctx["cfg"].bitrix_webhook_token,
    )
    project.refresh_from_db()
    assert project.stage == "lead"
    assert project.external_ids["bitrix_stage_conflict"]["bitrix_stage"] == "package_ready"

    client.force_login(p7_ctx["user"])
    resp = client.post(reverse("invest-project-bitrix-conflict", args=[project.pk]), {"resolution": "bitrix"})

    assert resp.status_code == 302
    project.refresh_from_db()
    assert project.stage == "package_ready"
    assert "bitrix_stage_conflict" not in project.external_ids


@pytest.mark.django_db
def test_project_detail_push_shows_gate_blockers(client, p7_ctx):
    project = InvestProject.objects.create(
        subsystem=p7_ctx["sub"],
        organization=p7_ctx["org"],
        code="P7-BLOCK",
        name="Blocked",
        stage="lead",
    )
    client.force_login(p7_ctx["user"])

    page = client.get(reverse("invest-project-detail", args=[project.pk]))
    assert page.status_code == 200
    assert "Отправить в Bitrix".encode("utf-8") in page.content
    assert "Заполните обязательные пункты пакета".encode("utf-8") in page.content

    resp = client.post(reverse("invest-project-bitrix-push", args=[project.pk]))
    assert resp.status_code == 302
    assert InvestIntegrationEvent.objects.filter(project=project, event_type="deal.push_blocked").exists()


@pytest.mark.django_db
def test_automation_simulator_posts_sample_webhook(client, p7_ctx):
    client.force_login(p7_ctx["user"])

    resp = client.post(reverse("invest-automation-simulate"))

    assert resp.status_code == 302
    assert InvestProject.objects.filter(subsystem=p7_ctx["sub"], external_ids__bitrix_id="SIM-100").exists()
