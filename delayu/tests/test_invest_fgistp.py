"""Invest FGISTP records — lifecycle, map, package isogd, automation."""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from delayu.menu import build_menu_for_membership
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
    InvestFgistpRecord,
    InvestPackageItem,
    InvestProject,
    InvestProjectSite,
    InvestSite,
    InvestStopFactor,
)
from delayu.services.invest_booking import book_site
from delayu.services.invest_fgistp import (
    ensure_fgistp_for_site,
    expire_fgistp_records,
    fgistp_geometry_for_map,
    generate_mock_zones,
    import_fgistp_geometry,
    verify_fgistp,
)
from delayu.services.invest_flags import ensure_automation_config
from delayu.services.invest_package import ensure_package
from delayu.services.invest_roles import perm_for_role
from delayu.services.invest_smev import apply_smev_response, request_smev_fill

User = get_user_model()


@pytest.fixture
def fgistp_ctx(db):
    sub = Subsystem.objects.create(
        code="inv-fgistp", name="Invest FGISTP", industry_template="invest", status="active"
    )
    module = ModuleCatalog.objects.create(code="M22", name="Инвестпроекты")
    SubsystemModule.objects.create(subsystem=sub, module=module, enabled=True)
    org = Organization.objects.create(subsystem=sub, code="mo1", name="МО-1")
    role_agency = Role.objects.create(subsystem=sub, code="invest_agency", name="Агентство")
    RoleModulePermission.objects.create(role=role_agency, module=module, **perm_for_role("invest_agency", "M22"))
    user = User.objects.create_user("fgistp_user", password="x")
    membership = SubsystemMembership.objects.create(
        user=user, subsystem=sub, organization=org, role=role_agency, is_default=True
    )
    site = InvestSite.objects.create(
        subsystem=sub,
        organization=org,
        cadastral_number="23:43:0101001:99",
        name="ЗУ ФГИС ТП",
        status=InvestSite.Status.DRAFT,
        completeness_pct=80,
        latitude=Decimal("45.035470"),
        longitude=Decimal("38.975313"),
    )
    project = InvestProject.objects.create(
        subsystem=sub,
        organization=org,
        code="P-FG",
        name="Проект ФГИС ТП",
        funnel=InvestProject.Funnel.ATTRACTION,
        stage="lead",
    )
    InvestProjectSite.objects.create(project=project, site=site, role=InvestProjectSite.Role.PROPOSED)
    ensure_automation_config(sub)
    return {
        "sub": sub,
        "org": org,
        "site": site,
        "project": project,
        "user": user,
        "membership": membership,
    }


@pytest.mark.django_db
def test_request_lifecycle_and_menu(client, fgistp_ctx):
    record = ensure_fgistp_for_site(fgistp_ctx["site"], reason="manual", user=fgistp_ctx["user"], force=True)
    assert record.status == InvestFgistpRecord.Status.REQUESTED

    client.force_login(fgistp_ctx["user"])
    response = client.get(reverse("invest-fgistp"))
    assert response.status_code == 200
    assert record.cadastral_number in response.content.decode()
    assert "Сведения ФГИС ТП" in [item.get("name") for item in build_menu_for_membership(fgistp_ctx["membership"])]


@pytest.mark.django_db
def test_mock_zones_and_map_payload(fgistp_ctx):
    record = ensure_fgistp_for_site(fgistp_ctx["site"], reason="mock", user=fgistp_ctx["user"], force=True)
    generate_mock_zones(record, user=fgistp_ctx["user"])
    record.refresh_from_db()
    assert record.geometry_source == InvestFgistpRecord.GeometrySource.MOCK
    assert record.payload.get("zones")
    geom = fgistp_geometry_for_map(record)
    assert geom and len(geom["coords"]) >= 4


@pytest.mark.django_db
def test_verify_marks_isogd_package_item(fgistp_ctx):
    ensure_package(fgistp_ctx["project"])
    record = ensure_fgistp_for_site(
        fgistp_ctx["site"], reason="pkg", user=fgistp_ctx["user"], project=fgistp_ctx["project"], force=True
    )
    generate_mock_zones(record)
    verify_fgistp(record, user=fgistp_ctx["user"], attach=True)
    item = InvestPackageItem.objects.get(package__project=fgistp_ctx["project"], code="isogd")
    assert item.status == InvestPackageItem.Status.ATTACHED


@pytest.mark.django_db
def test_expire_creates_stop_factor(fgistp_ctx):
    record = ensure_fgistp_for_site(
        fgistp_ctx["site"], reason="sla", user=fgistp_ctx["user"], project=fgistp_ctx["project"], force=True
    )
    record.valid_until = (timezone.now() - timedelta(days=1)).date()
    record.status = InvestFgistpRecord.Status.ATTACHED
    record.save(update_fields=["valid_until", "status", "updated_at"])

    stats = expire_fgistp_records(subsystem=fgistp_ctx["sub"])
    assert stats["expired"] == 1
    assert InvestStopFactor.objects.filter(
        project=fgistp_ctx["project"],
        title__contains="просрочена",
        status=InvestStopFactor.Status.BLOCKING,
    ).exists()


@pytest.mark.django_db
def test_geojson_import(fgistp_ctx):
    record = ensure_fgistp_for_site(fgistp_ctx["site"], reason="import", user=fgistp_ctx["user"], force=True)
    payload = {
        "type": "Polygon",
        "coordinates": [[[38.97, 45.03], [38.98, 45.03], [38.98, 45.04], [38.97, 45.04], [38.97, 45.03]]],
    }
    import_fgistp_geometry(record, raw=json.dumps(payload), filename="zones.geojson")
    record.refresh_from_db()
    assert record.geometry_source == InvestFgistpRecord.GeometrySource.IMPORT
    assert record.status == InvestFgistpRecord.Status.RECEIVED


@pytest.mark.django_db
def test_booking_triggers_fgistp_request(fgistp_ctx):
    book_site(project=fgistp_ctx["project"], site=fgistp_ctx["site"], user=fgistp_ctx["user"])
    assert InvestFgistpRecord.objects.filter(
        site=fgistp_ctx["site"], status=InvestFgistpRecord.Status.REQUESTED
    ).exists()


@pytest.mark.django_db
def test_smev_apply_requests_fgistp_without_geometry(fgistp_ctx):
    req = request_smev_fill(site=fgistp_ctx["site"], user=fgistp_ctx["user"])
    apply_smev_response(request=req, user=fgistp_ctx["user"])
    assert InvestFgistpRecord.objects.filter(site=fgistp_ctx["site"]).exists()


@pytest.mark.django_db
def test_detail_mock_action(client, fgistp_ctx):
    record = ensure_fgistp_for_site(fgistp_ctx["site"], reason="ui", user=fgistp_ctx["user"], force=True)
    client.force_login(fgistp_ctx["user"])
    response = client.post(reverse("invest-fgistp-detail", args=[record.pk]), {"action": "mock"})
    assert response.status_code == 302
    record.refresh_from_db()
    assert record.geometry_source == InvestFgistpRecord.GeometrySource.MOCK
