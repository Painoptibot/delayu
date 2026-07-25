import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from delayu.forms_invest_automation import InvestAutomationConnectionForm
from delayu.models import ModuleCatalog, Organization, Role, RoleModulePermission, Subsystem, SubsystemMembership, SubsystemModule
from delayu.models_invest import InvestAutomationConfig, InvestIntegrationEvent, InvestProject, InvestSite, InvestSmevRequest
from delayu.services.invest_bitrix import resolve_bitrix_stage_conflict
from delayu.services.invest_flags import ensure_automation_config
from delayu.services.invest_roles import perm_for_role

User = get_user_model()


@pytest.fixture
def p4_ctx(db):
    subsystem = Subsystem.objects.create(
        code="inv-p4",
        name="Invest P4",
        industry_template="invest",
        status=Subsystem.Status.ACTIVE,
    )
    module = ModuleCatalog.objects.create(code="M22", name="Invest projects")
    SubsystemModule.objects.create(subsystem=subsystem, module=module, enabled=True)
    org = Organization.objects.create(subsystem=subsystem, code="mo-p4", name="P4 MO")
    role = Role.objects.create(subsystem=subsystem, code="invest_admin", name="Invest admin")
    RoleModulePermission.objects.create(role=role, module=module, **perm_for_role(role.code, "M22"))
    user = User.objects.create_user("p4_admin", password="x", is_superuser=True)
    SubsystemMembership.objects.create(
        user=user,
        subsystem=subsystem,
        organization=org,
        role=role,
        is_default=True,
    )
    project = InvestProject.objects.create(
        subsystem=subsystem,
        organization=org,
        code="P4-1",
        name="P4 project",
        stage="lead",
        external_ids={
            "bitrix_stage_conflict": {
                "bitrix_stage_id": "SITE",
                "bitrix_funnel": "attraction",
                "bitrix_stage": "site_pick",
                "delayu_funnel": "attraction",
                "delayu_stage": "lead",
                "detected_at": "2026-07-25T10:00:00+00:00",
            }
        },
    )
    site = InvestSite.objects.create(
        subsystem=subsystem,
        organization=org,
        cadastral_number="23:04:0000000:16",
        name="P4 site",
    )
    cfg = ensure_automation_config(subsystem)
    return {"subsystem": subsystem, "org": org, "role": role, "user": user, "project": project, "site": site, "cfg": cfg}


@pytest.mark.django_db
def test_operator_integration_inbox_lists_retryable_events_and_requeues_one(client, p4_ctx):
    dead = InvestIntegrationEvent.objects.create(
        subsystem=p4_ctx["subsystem"],
        project=p4_ctx["project"],
        direction=InvestIntegrationEvent.Direction.OUT,
        channel=InvestIntegrationEvent.Channel.BITRIX,
        status=InvestIntegrationEvent.Status.DEAD,
        correlation_id="dead-16",
        event_type="deal.push",
        error_message="transport failed",
        retries=3,
        max_retries=3,
    )
    InvestIntegrationEvent.objects.create(
        subsystem=p4_ctx["subsystem"],
        direction=InvestIntegrationEvent.Direction.IN,
        channel=InvestIntegrationEvent.Channel.BITRIX,
        status=InvestIntegrationEvent.Status.DONE,
        correlation_id="done-16",
        event_type="deal.upsert",
    )
    client.force_login(p4_ctx["user"])

    page = client.get(reverse("invest-integrations-inbox"))

    assert page.status_code == 200
    html = page.content.decode()
    assert "dead-16" in html
    assert "done-16" not in html
    assert "Повторить" in html

    response = client.post(reverse("invest-integrations-inbox"), {"event_id": dead.pk}, follow=True)

    assert response.status_code == 200
    dead.refresh_from_db()
    assert dead.status == InvestIntegrationEvent.Status.QUEUED
    assert dead.retries == 0
    assert dead.error_message == ""


@pytest.mark.django_db
def test_stage_conflict_resolution_appends_history_log(p4_ctx):
    result = resolve_bitrix_stage_conflict(project=p4_ctx["project"], resolution="bitrix")

    assert result["resolved"] is True
    p4_ctx["project"].refresh_from_db()
    ext = p4_ctx["project"].external_ids
    assert "bitrix_stage_conflict" not in ext
    assert ext["bitrix_stage_conflict_log"][0]["resolution"] == "bitrix"
    assert ext["bitrix_stage_conflict_log"][0]["bitrix_stage"] == "site_pick"
    assert ext["bitrix_stage_conflict_log"][0]["delayu_stage"] == "lead"
    assert ext["bitrix_stage_conflict_log"][0]["resolved_at"]


@pytest.mark.django_db
def test_smev_batch_creates_mock_requests_for_matching_cadastral_numbers(client, p4_ctx):
    other = InvestSite.objects.create(
        subsystem=p4_ctx["subsystem"],
        organization=p4_ctx["org"],
        cadastral_number="23:04:0000000:17",
        name="P4 second site",
    )
    client.force_login(p4_ctx["user"])

    response = client.post(
        reverse("invest-sites-smev-batch"),
        {"cadastral_numbers": f"{p4_ctx['site'].cadastral_number}\n{other.cadastral_number}\n00:missing"},
        follow=True,
    )

    assert response.status_code == 200
    requests = InvestSmevRequest.objects.filter(subsystem=p4_ctx["subsystem"]).order_by("site__cadastral_number")
    assert [req.site.cadastral_number for req in requests] == [
        "23:04:0000000:16",
        "23:04:0000000:17",
    ]
    assert all(req.is_mock for req in requests)
    assert "СМЭВ batch" in response.content.decode()


@pytest.mark.django_db
def test_status_page_shows_external_connector_stubs(client, p4_ctx):
    p4_ctx["cfg"].flags = {
        **p4_ctx["cfg"].get_flags(),
        "rgis_connector": True,
        "isogd_connector": False,
    }
    p4_ctx["cfg"].save(update_fields=["flags"])
    client.force_login(p4_ctx["user"])

    response = client.get(reverse("invest-automation-status"))

    assert response.status_code == 200
    html = response.content.decode()
    assert "РГИС" in html
    assert "ИСОГД" in html
    assert "rgis_connector" in html
    assert "isogd_connector" in html


@pytest.mark.django_db
def test_webhook_connection_form_keeps_allowed_ips_ui_and_requires_token_when_inbound(client, p4_ctx):
    p4_ctx["cfg"].flags = {**p4_ctx["cfg"].get_flags(), "bitrix_inbound": True}
    p4_ctx["cfg"].bitrix_webhook_token = ""
    p4_ctx["cfg"].save(update_fields=["flags", "bitrix_webhook_token"])
    client.force_login(p4_ctx["user"])

    page = client.get(reverse("invest-automation"))

    assert page.status_code == 200
    html = page.content.decode()
    assert "allowed_ips" in html
    assert "JSON-массив IP-адресов" in html

    form = InvestAutomationConnectionForm(
        data={
            "bitrix_api_base": "",
            "bitrix_webhook_token": "",
            "allowed_ips": [],
            "contract_version": "v1",
        },
        instance=InvestAutomationConfig.objects.get(pk=p4_ctx["cfg"].pk),
    )
    assert form.is_valid() is False
    assert "bitrix_webhook_token" in form.errors
