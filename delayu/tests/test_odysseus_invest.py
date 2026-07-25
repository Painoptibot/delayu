from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from delayu.models import (
    AuditLog,
    ModuleCatalog,
    Organization,
    Role,
    RoleModulePermission,
    Subsystem,
    SubsystemMembership,
    SubsystemModule,
)
from delayu.models_invest import InvestProject, InvestSite
from delayu.services.invest_roles import perm_for_role
from delayu.services.odysseus_invest import build_invest_odysseus_context
from delayu.services.odysseus_settings import ensure_odysseus_settings

User = get_user_model()


@pytest.fixture
def invest_odysseus_ctx(db):
    sub = Subsystem.objects.create(
        code="inv-ody", name="Invest Odysseus", industry_template="invest", status="active"
    )
    module22 = ModuleCatalog.objects.create(code="M22", name="Инвестпроекты")
    module87 = ModuleCatalog.objects.create(code="M87", name="Odysseus workspace")
    SubsystemModule.objects.create(subsystem=sub, module=module22, enabled=True)
    SubsystemModule.objects.create(subsystem=sub, module=module87, enabled=True)
    org = Organization.objects.create(subsystem=sub, code="mo1", name="МО-1")
    roles = {}
    users = {}
    memberships = {}
    for code, name in [
        ("invest_admin", "Администратор"),
        ("invest_dept", "Департамент"),
        ("invest_agency", "Агентство"),
    ]:
        role = Role.objects.create(subsystem=sub, code=code, name=name)
        RoleModulePermission.objects.create(role=role, module=module22, **perm_for_role(code, "M22"))
        RoleModulePermission.objects.create(role=role, module=module87, can_view=True)
        user = User.objects.create_user(f"ody_{code}", password="x")
        membership = SubsystemMembership.objects.create(
            user=user, subsystem=sub, organization=org, role=role, is_default=True
        )
        roles[code] = role
        users[code] = user
        memberships[code] = membership
    project = InvestProject.objects.create(
        subsystem=sub,
        organization=org,
        code="P-ODY-1",
        name="Проект Odysseus",
        investor_name="Инвестор",
        stage="lead",
    )
    site = InvestSite.objects.create(
        subsystem=sub,
        organization=org,
        cadastral_number="23:43:0101001:77",
        name="Площадка Odysseus",
        status=InvestSite.Status.ACTUAL,
        completeness_pct=45,
    )
    cfg = ensure_odysseus_settings(sub)
    cfg.enabled = True
    cfg.save(update_fields=["enabled"])
    return {
        "sub": sub,
        "org": org,
        "roles": roles,
        "users": users,
        "memberships": memberships,
        "project": project,
        "site": site,
        "cfg": cfg,
    }


@pytest.mark.django_db
def test_allowlisted_role_gets_project_cta_and_open_redirect(client, invest_odysseus_ctx):
    client.force_login(invest_odysseus_ctx["users"]["invest_dept"])

    response = client.get(reverse("invest-project-detail", args=[invest_odysseus_ctx["project"].pk]))

    assert response.status_code == 200
    html = response.content.decode()
    assert "Открыть в Odysseus" in html
    assert reverse("invest-odysseus-open") in html

    response = client.get(
        reverse("invest-odysseus-open"),
        {"project": invest_odysseus_ctx["project"].pk},
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("platform-odysseus")
    ctx = client.session["odysseus_invest_context"]
    assert ctx["project_id"] == invest_odysseus_ctx["project"].pk
    assert ctx["snapshot"]["project"]["code"] == "P-ODY-1"
    assert AuditLog.objects.filter(action="odysseus.invest.open", object_id=str(invest_odysseus_ctx["project"].pk)).exists()


@pytest.mark.django_db
def test_agency_without_allowlist_does_not_get_cta(client, invest_odysseus_ctx):
    client.force_login(invest_odysseus_ctx["users"]["invest_agency"])

    response = client.get(reverse("invest-hub"))

    assert response.status_code == 200
    assert "Открыть в Odysseus" not in response.content.decode()


@pytest.mark.django_db
def test_disabled_settings_hide_site_cta(client, invest_odysseus_ctx):
    invest_odysseus_ctx["cfg"].enabled = False
    invest_odysseus_ctx["cfg"].save(update_fields=["enabled"])
    client.force_login(invest_odysseus_ctx["users"]["invest_admin"])

    response = client.get(reverse("invest-site-detail", args=[invest_odysseus_ctx["site"].pk]))

    assert response.status_code == 200
    assert "Открыть в Odysseus" not in response.content.decode()


@pytest.mark.django_db
def test_build_context_includes_compact_site_snapshot(invest_odysseus_ctx):
    ctx = build_invest_odysseus_context(
        subsystem=invest_odysseus_ctx["sub"],
        site=invest_odysseus_ctx["site"],
    )

    assert ctx["subsystem_code"] == "inv-ody"
    assert ctx["site_id"] == invest_odysseus_ctx["site"].pk
    assert ctx["snapshot"]["site"]["cadastral_number"] == "23:43:0101001:77"
    assert "prompt_template" in ctx
