"""Invest open-data verification Wave 1 / P0."""

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from delayu.models import (
    ModuleCatalog,
    Organization,
    Role,
    RoleModulePermission,
    Subsystem,
    SubsystemMembership,
    SubsystemModule,
)
from delayu.models_invest import (
    InvestInvestor,
    InvestPackageItem,
    InvestProject,
    InvestProjectSite,
    InvestSite,
    InvestStopFactor,
    InvestVerificationRun,
)
from delayu.services.invest_flags import ensure_automation_config
from delayu.services.invest_opendata import run_investor_verification, run_project_verification, run_site_verification
from delayu.services.invest_opendata.mock_fixtures import CLEAN_INN, HARD_BANKRUPT_INN
from delayu.services.invest_opendata.stop_factors import STOP_PREFIX
from delayu.services.invest_package import ensure_package
from delayu.services.invest_roles import perm_for_role

User = get_user_model()


@pytest.fixture
def opendata_ctx(db):
    sub = Subsystem.objects.create(
        code="inv-opendata",
        name="Invest OpenData",
        industry_template="invest",
        status="active",
    )
    module = ModuleCatalog.objects.create(code="M22", name="Инвестпроекты")
    SubsystemModule.objects.create(subsystem=sub, module=module, enabled=True)
    org = Organization.objects.create(subsystem=sub, code="mo1", name="МО-1")
    role = Role.objects.create(subsystem=sub, code="invest_agency", name="Агентство")
    RoleModulePermission.objects.create(role=role, module=module, **perm_for_role("invest_agency", "M22"))
    user = User.objects.create_user("opendata_user", password="x")
    SubsystemMembership.objects.create(
        user=user, subsystem=sub, organization=org, role=role, is_default=True
    )
    investor = InvestInvestor.objects.create(
        subsystem=sub, name="Инвестор OpenData", inn=CLEAN_INN
    )
    project = InvestProject.objects.create(
        subsystem=sub,
        organization=org,
        code="P-OD",
        name="Проект OpenData",
        funnel=InvestProject.Funnel.ATTRACTION,
        stage="lead",
        investor_entity=investor,
        investor_name=investor.name,
    )
    site = InvestSite.objects.create(
        subsystem=sub,
        organization=org,
        cadastral_number="23:43:0101001:55",
        name="ЗУ OpenData",
        status=InvestSite.Status.DRAFT,
        completeness_pct=70,
        latitude=Decimal("45.035470"),
        longitude=Decimal("38.975313"),
    )
    InvestProjectSite.objects.create(
        project=project, site=site, role=InvestProjectSite.Role.PROPOSED
    )
    ensure_automation_config(sub)
    ensure_package(project)
    return {
        "sub": sub,
        "org": org,
        "user": user,
        "investor": investor,
        "project": project,
        "site": site,
    }


@pytest.mark.django_db
def test_investor_mock_run_stores_snapshot(opendata_ctx):
    investor = opendata_ctx["investor"]
    with patch("delayu.services.invest_opendata.http.opendata_get") as http_get:
        run = run_investor_verification(investor, user=opendata_ctx["user"])
        http_get.assert_not_called()
    assert run.status == InvestVerificationRun.Status.DONE
    assert run.source_results.count() == 8
    investor.refresh_from_db()
    snap = (investor.extras or {}).get("opendata") or {}
    assert snap.get("run_id") == run.pk
    assert snap.get("summary", {}).get("sources_total") == 8
    assert snap.get("summary", {}).get("hard_count") == 0
    item = InvestPackageItem.objects.get(
        package__project=opendata_ctx["project"], code="opendata"
    )
    assert item.status == InvestPackageItem.Status.ATTACHED


@pytest.mark.django_db
def test_bankrupt_creates_stop_factor_then_clean_resolves(opendata_ctx):
    investor = opendata_ctx["investor"]
    project = opendata_ctx["project"]
    investor.inn = HARD_BANKRUPT_INN
    investor.save(update_fields=["inn", "updated_at"])

    run1 = run_investor_verification(investor)
    assert (run1.summary or {}).get("hard_count", 0) >= 1
    assert InvestStopFactor.objects.filter(
        project=project,
        title__startswith=STOP_PREFIX,
        status=InvestStopFactor.Status.BLOCKING,
    ).exists()

    investor.inn = CLEAN_INN
    investor.save(update_fields=["inn", "updated_at"])
    run2 = run_investor_verification(investor)
    assert (run2.summary or {}).get("hard_count", 0) == 0
    assert not InvestStopFactor.objects.filter(
        project=project,
        title__startswith=STOP_PREFIX,
        status__in=(InvestStopFactor.Status.OPEN, InvestStopFactor.Status.BLOCKING),
    ).exists()
    assert InvestStopFactor.objects.filter(
        project=project,
        title__startswith=STOP_PREFIX,
        status=InvestStopFactor.Status.RESOLVED,
    ).exists()


@pytest.mark.django_db
def test_site_run_uses_local_adapters(opendata_ctx):
    site = opendata_ctx["site"]
    with patch("delayu.services.invest_opendata.http.opendata_get") as http_get:
        run = run_site_verification(site)
        http_get.assert_not_called()
    assert run.status == InvestVerificationRun.Status.DONE
    codes = set(run.source_results.values_list("source_code", flat=True))
    assert codes == {"nspd_public", "fgistp_public", "mnp_local"}
    site.refresh_from_db()
    assert "opendata" in (site.external_ids or {})


@pytest.mark.django_db
def test_project_verification_ui(client, opendata_ctx):
    project = opendata_ctx["project"]
    client.force_login(opendata_ctx["user"])
    response = client.post(reverse("invest-verification-project", args=[project.pk]))
    assert response.status_code == 302
    project.refresh_from_db()
    assert "opendata" in (project.external_ids or {})
    detail = client.get(reverse("invest-project-detail", args=[project.pk]))
    assert detail.status_code == 200
    html = detail.content.decode()
    assert "opendata-results" in html
    assert "ЕГРЮЛ" in html or "egrul_fns" in html


@pytest.mark.django_db
def test_opendata_catalog_lists_sources(client, opendata_ctx):
    client.force_login(opendata_ctx["user"])
    response = client.get(reverse("invest-opendata-catalog"))
    assert response.status_code == 200
    html = response.content.decode()
    assert "Наборы источников" in html
    assert "egrul_fns" in html
    assert "nspd_public" in html
    assert "mnp_local" in html
