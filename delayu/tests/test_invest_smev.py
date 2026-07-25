"""Тесты mock-СМЭВ автозаполнения площадок."""

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
from delayu.models_invest import InvestSite, InvestSmevRequest
from delayu.services.invest_roles import perm_for_role
from delayu.services.invest_smev import apply_smev_response, request_smev_fill

User = get_user_model()


@pytest.fixture
def smev_ctx(db):
    sub = Subsystem.objects.create(
        code="inv-smev", name="Invest SMEV", industry_template="invest", status="active"
    )
    module = ModuleCatalog.objects.create(code="M22", name="Инвестпроекты")
    SubsystemModule.objects.create(subsystem=sub, module=module, enabled=True)
    org = Organization.objects.create(subsystem=sub, code="mo1", name="МО-1")
    role = Role.objects.create(subsystem=sub, code="invest_agency", name="Агентство")
    RoleModulePermission.objects.create(role=role, module=module, **perm_for_role(role.code, "M22"))
    user = User.objects.create_user("invest_smev_agency", password="x")
    SubsystemMembership.objects.create(
        user=user, subsystem=sub, organization=org, role=role, is_default=True
    )
    site = InvestSite.objects.create(
        subsystem=sub,
        organization=org,
        cadastral_number="23:43:0101001:42",
        name="ЗУ демо",
        status=InvestSite.Status.DRAFT,
        completeness_pct=10,
    )
    return {"user": user, "site": site, "sub": sub}


@pytest.mark.django_db
def test_request_smev_fill_creates_mock_egrn_payload(smev_ctx):
    site = smev_ctx["site"]
    req = request_smev_fill(site=site, user=smev_ctx["user"])
    assert req.is_mock is True
    assert req.status == InvestSmevRequest.Status.DONE
    assert req.service == InvestSmevRequest.Service.EGRN
    assert req.response_payload["cadastral_number"] == site.cadastral_number
    assert "area_ha" in req.response_payload
    site.refresh_from_db()
    assert site.last_smev_at is not None


@pytest.mark.django_db
def test_apply_smev_response_fills_site_card(smev_ctx):
    site = smev_ctx["site"]
    req = request_smev_fill(site=site, user=smev_ctx["user"])
    apply_smev_response(request=req)
    site.refresh_from_db()
    req.refresh_from_db()
    assert site.address
    assert site.area_ha is not None
    assert site.land_category
    assert site.vri
    assert site.right_type
    assert site.latitude is not None
    assert site.longitude is not None
    assert site.egrn_updated_at is not None
    assert site.completeness_pct >= 40
    assert site.status == InvestSite.Status.IN_REVIEW
    assert req.status == InvestSmevRequest.Status.APPLIED


@pytest.mark.django_db
def test_smev_request_and_apply_via_views(client, smev_ctx):
    client.force_login(smev_ctx["user"])
    site = smev_ctx["site"]
    detail_url = reverse("invest-site-detail", args=[site.pk])
    assert client.get(detail_url).status_code == 200

    resp = client.post(
        reverse("invest-site-smev-request", args=[site.pk]),
        {"service": "egrn"},
    )
    assert resp.status_code == 302
    req = InvestSmevRequest.objects.get(site=site)
    assert req.status == InvestSmevRequest.Status.DONE

    resp = client.post(reverse("invest-site-smev-apply", args=[site.pk, req.pk]))
    assert resp.status_code == 302
    site.refresh_from_db()
    assert site.address.startswith("Краснодарский край")


@pytest.mark.django_db
def test_site_edit_form_uses_bootstrap_classes(client, smev_ctx):
    client.force_login(smev_ctx["user"])
    resp = client.get(reverse("invest-site-edit", args=[smev_ctx["site"].pk]))
    assert resp.status_code == 200
    html = resp.content.decode()
    assert 'class="form-control"' in html or "form-control" in html
    assert "form-select" in html
    assert 'class="form-label"' in html
