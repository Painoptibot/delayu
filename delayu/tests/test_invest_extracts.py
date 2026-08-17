"""Invest extracts (выкопировки) — lifecycle, map, package, automation."""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
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
    InvestExtract,
    InvestPackageItem,
    InvestProject,
    InvestProjectSite,
    InvestSite,
    InvestStopFactor,
)
from delayu.services.invest_booking import book_site
from delayu.services.invest_extracts import (
    ensure_extract_for_site,
    expire_extracts,
    extract_geometry_for_map,
    generate_mock_contour,
    import_extract_geometry,
    verify_extract,
)
from delayu.services.invest_flags import ensure_automation_config
from delayu.services.invest_package import ensure_package
from delayu.services.invest_roles import perm_for_role
from delayu.services.invest_smev import apply_smev_response, request_smev_fill

User = get_user_model()


@pytest.fixture
def extract_ctx(db):
    sub = Subsystem.objects.create(
        code="inv-extract", name="Invest Extracts", industry_template="invest", status="active"
    )
    module = ModuleCatalog.objects.create(code="M22", name="Инвестпроекты")
    SubsystemModule.objects.create(subsystem=sub, module=module, enabled=True)
    org = Organization.objects.create(subsystem=sub, code="mo1", name="МО-1")
    role_agency = Role.objects.create(subsystem=sub, code="invest_agency", name="Агентство")
    RoleModulePermission.objects.create(role=role_agency, module=module, **perm_for_role("invest_agency", "M22"))
    user = User.objects.create_user("extract_user", password="x")
    membership = SubsystemMembership.objects.create(
        user=user, subsystem=sub, organization=org, role=role_agency, is_default=True
    )
    site = InvestSite.objects.create(
        subsystem=sub,
        organization=org,
        cadastral_number="23:43:0101001:77",
        name="ЗУ выкопировка",
        status=InvestSite.Status.DRAFT,
        completeness_pct=80,
        latitude=Decimal("45.035470"),
        longitude=Decimal("38.975313"),
    )
    project = InvestProject.objects.create(
        subsystem=sub,
        organization=org,
        code="P-EX",
        name="Проект выкопировки",
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
def test_request_lifecycle_and_menu(client, extract_ctx):
    extract = ensure_extract_for_site(extract_ctx["site"], reason="manual", user=extract_ctx["user"], force=True)
    assert extract.status == InvestExtract.Status.REQUESTED
    assert extract.sla_due_at is not None

    client.force_login(extract_ctx["user"])
    response = client.get(reverse("invest-extracts"))
    assert response.status_code == 200
    assert extract.cadastral_number in response.content.decode()

    menu_labels = [item.get("name") for item in build_menu_for_membership(extract_ctx["membership"])]
    assert "Выкопировки" in menu_labels


@pytest.mark.django_db
def test_mock_contour_and_map_payload(extract_ctx):
    extract = ensure_extract_for_site(extract_ctx["site"], reason="mock", user=extract_ctx["user"], force=True)
    generate_mock_contour(extract, user=extract_ctx["user"])
    extract.refresh_from_db()
    assert extract.geometry_source == InvestExtract.GeometrySource.MOCK
    assert extract.geometry.get("type") == "Polygon"
    geom = extract_geometry_for_map(extract)
    assert geom and len(geom["coords"]) >= 4


@pytest.mark.django_db
def test_verify_marks_package_item(extract_ctx):
    ensure_package(extract_ctx["project"])
    extract = ensure_extract_for_site(
        extract_ctx["site"], reason="pkg", user=extract_ctx["user"], project=extract_ctx["project"], force=True
    )
    generate_mock_contour(extract)
    verify_extract(extract, user=extract_ctx["user"], attach=True)
    item = InvestPackageItem.objects.get(package__project=extract_ctx["project"], code="extract")
    assert item.status == InvestPackageItem.Status.ATTACHED
    assert not InvestStopFactor.objects.filter(
        project=extract_ctx["project"],
        status__in=(InvestStopFactor.Status.OPEN, InvestStopFactor.Status.BLOCKING),
        title__contains=extract_ctx["site"].cadastral_number,
    ).exists()


@pytest.mark.django_db
def test_expire_creates_stop_factor(extract_ctx):
    extract = ensure_extract_for_site(
        extract_ctx["site"], reason="sla", user=extract_ctx["user"], project=extract_ctx["project"], force=True
    )
    extract.valid_until = (timezone.now() - timedelta(days=1)).date()
    extract.status = InvestExtract.Status.ATTACHED
    extract.save(update_fields=["valid_until", "status", "updated_at"])

    stats = expire_extracts(subsystem=extract_ctx["sub"])
    assert stats["expired"] == 1
    extract.refresh_from_db()
    assert extract.status == InvestExtract.Status.EXPIRED
    assert InvestStopFactor.objects.filter(
        project=extract_ctx["project"],
        title__contains="просрочена",
        status=InvestStopFactor.Status.BLOCKING,
    ).exists()


@pytest.mark.django_db
def test_geojson_import(extract_ctx):
    extract = ensure_extract_for_site(extract_ctx["site"], reason="import", user=extract_ctx["user"], force=True)
    payload = {
        "type": "Polygon",
        "coordinates": [
            [
                [38.97, 45.03],
                [38.98, 45.03],
                [38.98, 45.04],
                [38.97, 45.04],
                [38.97, 45.03],
            ]
        ],
    }
    import_extract_geometry(extract, raw=json.dumps(payload), filename="plot.geojson")
    extract.refresh_from_db()
    assert extract.geometry_source == InvestExtract.GeometrySource.IMPORT
    assert extract.status == InvestExtract.Status.RECEIVED


@pytest.mark.django_db
def test_booking_triggers_extract_request(extract_ctx):
    book_site(project=extract_ctx["project"], site=extract_ctx["site"], user=extract_ctx["user"])
    assert InvestExtract.objects.filter(
        site=extract_ctx["site"], status=InvestExtract.Status.REQUESTED
    ).exists()


@pytest.mark.django_db
def test_smev_apply_requests_extract_without_geometry(extract_ctx):
    req = request_smev_fill(site=extract_ctx["site"], user=extract_ctx["user"])
    apply_smev_response(request=req, user=extract_ctx["user"])
    assert InvestExtract.objects.filter(site=extract_ctx["site"]).exists()


@pytest.mark.django_db
def test_detail_mock_action(client, extract_ctx):
    extract = ensure_extract_for_site(extract_ctx["site"], reason="ui", user=extract_ctx["user"], force=True)
    client.force_login(extract_ctx["user"])
    response = client.post(reverse("invest-extract-detail", args=[extract.pk]), {"action": "mock"})
    assert response.status_code == 302
    extract.refresh_from_db()
    assert extract.geometry_source == InvestExtract.GeometrySource.MOCK


@pytest.mark.django_db
def test_upload_file_marks_received(client, extract_ctx):
    extract = ensure_extract_for_site(extract_ctx["site"], reason="upload", user=extract_ctx["user"], force=True)
    client.force_login(extract_ctx["user"])
    upload = SimpleUploadedFile("plan.pdf", b"%PDF-1.4 mock", content_type="application/pdf")
    response = client.post(
        reverse("invest-extract-detail", args=[extract.pk]),
        {"action": "upload", "file": upload},
    )
    assert response.status_code == 302
    extract.refresh_from_db()
    assert extract.status == InvestExtract.Status.RECEIVED
    assert extract.file


@pytest.mark.django_db
def test_geometries_intersect_helper():
    from delayu.services.invest_extract_mnp import geometries_intersect

    a = {
        "type": "Polygon",
        "coordinates": [[[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0], [0.0, 0.0]]],
    }
    b = {
        "type": "Polygon",
        "coordinates": [[[1.0, 1.0], [3.0, 1.0], [3.0, 3.0], [1.0, 3.0], [1.0, 1.0]]],
    }
    far = {
        "type": "Polygon",
        "coordinates": [[[10.0, 10.0], [11.0, 10.0], [11.0, 11.0], [10.0, 11.0], [10.0, 10.0]]],
    }
    assert geometries_intersect(a, b) is True
    assert geometries_intersect(a, far) is False


@pytest.mark.django_db
def test_refresh_mnp_intersections_snapshot_and_hard_stop(extract_ctx, settings):
    from delayu.models_invest import InvestMnpFeature, InvestMnpScheme
    from delayu.services.invest_extract_mnp import MNP_STOP_PREFIX, refresh_extract_mnp_intersections

    settings.INVEST_MNP_EXTRACT_HARD_CLASSIDS = "701010800"
    ensure_package(extract_ctx["project"])
    extract = ensure_extract_for_site(
        extract_ctx["site"],
        reason="mnp",
        user=extract_ctx["user"],
        project=extract_ctx["project"],
        force=True,
    )
    geom = {
        "type": "Polygon",
        "coordinates": [
            [
                [38.970, 45.030],
                [38.980, 45.030],
                [38.980, 45.040],
                [38.970, 45.040],
                [38.970, 45.030],
            ]
        ],
    }
    extract.geometry = geom
    extract.geometry_source = InvestExtract.GeometrySource.IMPORT
    extract.save(update_fields=["geometry", "geometry_source", "updated_at"])

    scheme = InvestMnpScheme.objects.create(
        uin="0372000002020302202407259",
        name="Генплан тест",
        status=InvestMnpScheme.Status.READY,
        feature_count=2,
    )
    InvestMnpFeature.objects.create(
        scheme=scheme,
        external_id="hard-1",
        classid="701010800",
        class_name="Охрана",
        properties={"name": "Зона жёсткая"},
        geometry={
            "type": "Polygon",
            "coordinates": [
                [
                    [38.972, 45.032],
                    [38.978, 45.032],
                    [38.978, 45.038],
                    [38.972, 45.038],
                    [38.972, 45.032],
                ]
            ],
        },
        bbox_min_lon=38.972,
        bbox_min_lat=45.032,
        bbox_max_lon=38.978,
        bbox_max_lat=45.038,
    )
    InvestMnpFeature.objects.create(
        scheme=scheme,
        external_id="soft-1",
        classid="701010101",
        class_name="Жилая",
        properties={"name": "Зона мягкая"},
        geometry={
            "type": "Polygon",
            "coordinates": [
                [
                    [38.971, 45.031],
                    [38.975, 45.031],
                    [38.975, 45.035],
                    [38.971, 45.035],
                    [38.971, 45.031],
                ]
            ],
        },
        bbox_min_lon=38.971,
        bbox_min_lat=45.031,
        bbox_max_lon=38.975,
        bbox_max_lat=45.035,
    )

    snap = refresh_extract_mnp_intersections(extract)
    extract.refresh_from_db()
    stored = (extract.external_ids or {}).get("mnp_intersections") or {}
    assert stored.get("count") == 2
    assert stored.get("hard_count") == 1
    assert snap["hard_count"] == 1
    assert InvestStopFactor.objects.filter(
        project=extract_ctx["project"],
        title__startswith=MNP_STOP_PREFIX,
        status=InvestStopFactor.Status.BLOCKING,
    ).exists()


@pytest.mark.django_db
def test_detail_exposes_mnp_ui_and_recalc(client, extract_ctx, settings):
    settings.YANDEX_MAPS_API_KEY = "test-key"
    extract = ensure_extract_for_site(extract_ctx["site"], reason="ui-mnp", user=extract_ctx["user"], force=True)
    payload = {
        "type": "Polygon",
        "coordinates": [
            [
                [38.97, 45.03],
                [38.98, 45.03],
                [38.98, 45.04],
                [38.97, 45.04],
                [38.97, 45.03],
            ]
        ],
    }
    import_extract_geometry(extract, raw=json.dumps(payload), filename="plot.geojson")
    client.force_login(extract_ctx["user"])

    response = client.get(reverse("invest-extract-detail", args=[extract.pk]))
    assert response.status_code == 200
    html = response.content.decode()
    assert 'id="mnp-zones-block"' in html
    assert "Зоны генплана" in html
    assert 'id="mnp-auto-toggle"' in html
    assert 'id="map-annotation"' in html
    assert "mnp_config_json" in response.context or "viewportProxy" in html

    response = client.post(reverse("invest-extract-detail", args=[extract.pk]), {"action": "recalc_mnp"})
    assert response.status_code == 302
    extract.refresh_from_db()
    assert "mnp_intersections" in (extract.external_ids or {})
    assert "count" in extract.external_ids["mnp_intersections"]
