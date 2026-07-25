# delayu/tests/test_invest_automation_ui.py
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from delayu.models import ModuleCatalog, Organization, Role, RoleModulePermission, Subsystem, SubsystemMembership, SubsystemModule
from delayu.forms_invest_automation import (
    InvestAutomationConnectionForm,
    InvestAutomationFlagsForm,
    InvestAutomationMappingForm,
)
from delayu.services.invest_automation_access import user_can_manage_invest_automation
from delayu.services.invest_flags import ensure_automation_config
from delayu.services.invest_roles import perm_for_role

User = get_user_model()


@pytest.fixture
def invest_roles_ctx(db):
    sub = Subsystem.objects.create(
        code="inv-ui", name="Invest UI", industry_template="invest", status="active"
    )
    module = ModuleCatalog.objects.create(code="M22", name="Инвестпроекты")
    SubsystemModule.objects.create(subsystem=sub, module=module, enabled=True)
    org = Organization.objects.create(subsystem=sub, code="dept", name="Dept")
    roles = {}
    for code, name in [
        ("invest_admin", "Admin"),
        ("invest_agency", "Agency"),
    ]:
        role = Role.objects.create(subsystem=sub, code=code, name=name)
        RoleModulePermission.objects.create(role=role, module=module, **perm_for_role(code, "M22"))
        roles[code] = role
    return {"sub": sub, "org": org, "roles": roles, "module": module}


def _member(ctx, username, role_code, *, platform_admin=False):
    user = User.objects.create_user(username, password="x")
    if platform_admin:
        from delayu.models_business import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.is_platform_admin = True
        profile.save(update_fields=["is_platform_admin"])
    membership = SubsystemMembership.objects.create(
        user=user,
        subsystem=ctx["sub"],
        organization=ctx["org"],
        role=ctx["roles"][role_code],
        is_default=True,
    )
    return user, membership


@pytest.mark.django_db
def test_access_invest_admin_allowed(invest_roles_ctx):
    user, membership = _member(invest_roles_ctx, "adm", "invest_admin")
    assert user_can_manage_invest_automation(user, membership) is True


@pytest.mark.django_db
def test_access_agency_denied(invest_roles_ctx):
    user, membership = _member(invest_roles_ctx, "ag", "invest_agency")
    assert user_can_manage_invest_automation(user, membership) is False


@pytest.mark.django_db
def test_access_platform_admin_allowed(invest_roles_ctx):
    user, membership = _member(invest_roles_ctx, "padm", "invest_agency", platform_admin=True)
    assert user_can_manage_invest_automation(user, membership) is True


@pytest.mark.django_db
def test_access_superuser_allowed(invest_roles_ctx):
    user, membership = _member(invest_roles_ctx, "su", "invest_agency")
    user.is_superuser = True
    user.save(update_fields=["is_superuser"])
    assert user_can_manage_invest_automation(user, membership) is True


@pytest.mark.django_db
def test_connection_form_requires_token_when_inbound(invest_roles_ctx):
    cfg = ensure_automation_config(invest_roles_ctx["sub"])
    cfg.flags = {**cfg.get_flags(), "bitrix_inbound": True}
    cfg.bitrix_webhook_token = ""
    cfg.save()
    form = InvestAutomationConnectionForm(
        data={
            "bitrix_api_base": "https://example.bitrix24.ru/rest/",
            "bitrix_webhook_token": "",
            "contract_version": "v1",
        },
        instance=cfg,
    )
    assert form.is_valid() is False
    assert "bitrix_webhook_token" in form.errors


@pytest.mark.django_db
def test_flags_form_roundtrip(invest_roles_ctx):
    cfg = ensure_automation_config(invest_roles_ctx["sub"])
    form = InvestAutomationFlagsForm(
        data={"bitrix_inbound": "on", "sandbox": "on"},
        initial_flags=cfg.get_flags(),
    )
    assert form.is_valid()
    flags = form.cleaned_flags()
    assert flags["bitrix_inbound"] is True
    assert flags["sandbox"] is True
    assert flags["auto_smev"] is False  # unchecked checkbox


@pytest.mark.django_db
def test_mapping_form_parses_stage_pairs(invest_roles_ctx):
    form = InvestAutomationMappingForm(
        data={
            "field_rows": "TITLE=name\nUF_INVESTOR=investor_name",
            "stage_rows": "NEW=attraction/lead\nSUPPORT=support/accepted",
        }
    )
    assert form.is_valid()
    assert form.cleaned_field_mapping()["TITLE"] == "name"
    assert form.cleaned_stage_mapping()["NEW"] == ["attraction", "lead"]


@pytest.mark.django_db
def test_connection_get_ok_for_admin(client, invest_roles_ctx):
    user, _ = _member(invest_roles_ctx, "adm2", "invest_admin")
    ensure_automation_config(invest_roles_ctx["sub"])
    client.force_login(user)

    resp = client.get(reverse("invest-automation"))

    assert resp.status_code == 200
    assert b"bitrix" in resp.content.lower() or "Bitrix".encode() in resp.content


@pytest.mark.django_db
def test_connection_denied_for_agency(client, invest_roles_ctx):
    user, _ = _member(invest_roles_ctx, "ag2", "invest_agency")
    client.force_login(user)

    resp = client.get(reverse("invest-automation"))

    assert resp.status_code == 302
    assert resp["Location"] == reverse("invest-hub")


@pytest.mark.django_db
def test_connection_get_ok_for_platform_admin_without_m22(client, invest_roles_ctx):
    user, _ = _member(invest_roles_ctx, "padm2", "invest_agency", platform_admin=True)
    RoleModulePermission.objects.filter(
        role=invest_roles_ctx["roles"]["invest_agency"],
        module=invest_roles_ctx["module"],
    ).update(can_view=False, can_create=False, can_change=False, can_delete=False)
    ensure_automation_config(invest_roles_ctx["sub"])
    client.force_login(user)

    resp = client.get(reverse("invest-automation"))

    assert resp.status_code == 200


@pytest.mark.django_db
def test_connection_post_saves_token(client, invest_roles_ctx):
    user, _ = _member(invest_roles_ctx, "adm3", "invest_admin")
    cfg = ensure_automation_config(invest_roles_ctx["sub"])
    client.force_login(user)

    resp = client.post(
        reverse("invest-automation"),
        {
            "bitrix_api_base": "https://crm.example/rest/",
            "bitrix_webhook_token": "tok-demo-1",
            "contract_version": "v1",
        },
    )

    assert resp.status_code == 302
    cfg.refresh_from_db()
    assert cfg.bitrix_webhook_token == "tok-demo-1"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name",
    [
        "invest-automation-flags",
        "invest-automation-mapping",
        "invest-automation-status",
    ],
)
def test_placeholder_automation_tabs_get_ok_for_admin(client, invest_roles_ctx, url_name):
    user, _ = _member(invest_roles_ctx, f"{url_name}-adm", "invest_admin")
    ensure_automation_config(invest_roles_ctx["sub"])
    client.force_login(user)

    resp = client.get(reverse(url_name))

    assert resp.status_code == 200
