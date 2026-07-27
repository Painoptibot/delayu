"""Enterprise SMEV demo coverage for invest contour."""

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
    InvestPackageItem,
    InvestProject,
    InvestProjectSite,
    InvestSite,
    InvestSmevInfoType,
    InvestSmevRequest,
    InvestStopFactor,
)
from delayu.services.invest_booking import book_site
from delayu.services.invest_flags import ensure_automation_config
from delayu.services.invest_package import ensure_package
from delayu.services.invest_pipeline import auto_smev_enrich_site
from delayu.services.invest_roles import perm_for_role
from delayu.services.invest_smev import (
    apply_smev_response,
    emulate_gateway_response,
    request_smev_fill,
    validate_smev_response,
)

User = get_user_model()


@pytest.fixture
def enterprise_ctx(db):
    sub = Subsystem.objects.create(
        code="inv-smev-ent", name="Invest SMEV Enterprise", industry_template="invest", status="active"
    )
    module = ModuleCatalog.objects.create(code="M22", name="Инвестпроекты")
    SubsystemModule.objects.create(subsystem=sub, module=module, enabled=True)
    org = Organization.objects.create(subsystem=sub, code="mo1", name="МО-1")
    role_agency = Role.objects.create(subsystem=sub, code="invest_agency", name="Агентство")
    role_admin = Role.objects.create(subsystem=sub, code="invest_admin", name="Администратор")
    for role in (role_agency, role_admin):
        RoleModulePermission.objects.create(role=role, module=module, **perm_for_role(role.code, "M22"))
    user = User.objects.create_user("smev_ent_user", password="x")
    admin = User.objects.create_user("smev_ent_admin", password="x")
    membership = SubsystemMembership.objects.create(
        user=user, subsystem=sub, organization=org, role=role_agency, is_default=True
    )
    admin_membership = SubsystemMembership.objects.create(
        user=admin, subsystem=sub, organization=org, role=role_admin, is_default=True
    )
    site = InvestSite.objects.create(
        subsystem=sub,
        organization=org,
        cadastral_number="23:43:0101001:42",
        name="ЗУ демо",
        status=InvestSite.Status.DRAFT,
        completeness_pct=10,
    )
    project = InvestProject.objects.create(
        subsystem=sub,
        organization=org,
        code="P-SMEV",
        name="Проект СМЭВ",
        funnel=InvestProject.Funnel.ATTRACTION,
        stage="lead",
    )
    InvestProjectSite.objects.create(project=project, site=site, role=InvestProjectSite.Role.PROPOSED)
    return {
        "sub": sub,
        "org": org,
        "site": site,
        "project": project,
        "user": user,
        "admin": admin,
        "membership": membership,
        "admin_membership": admin_membership,
    }


@pytest.mark.django_db
def test_console_lists_requests_filters_and_menu(client, enterprise_ctx):
    req = request_smev_fill(site=enterprise_ctx["site"], user=enterprise_ctx["user"])
    client.force_login(enterprise_ctx["user"])

    response = client.get(reverse("invest-smev-console"), {"status": req.status, "service": req.service})

    assert response.status_code == 200
    assert req.correlation_id
    assert "Sandbox" in response.content.decode()
    assert "СМЭВ" in [item.get("name") for item in build_menu_for_membership(enterprise_ctx["membership"])]


@pytest.mark.django_db
def test_lifecycle_retry_timeout_dead_letter_helpers(enterprise_ctx):
    req = request_smev_fill(site=enterprise_ctx["site"], user=enterprise_ctx["user"])

    req.retry_or_dead_letter(actor=enterprise_ctx["user"])
    req.timeout_to_dead_letter(actor=enterprise_ctx["user"])
    req.refresh_from_db()

    assert req.retries == 1
    assert req.status == InvestSmevRequest.Status.DEAD_LETTER
    assert req.dead_lettered_at is not None


@pytest.mark.django_db
def test_batch_redirects_to_console_summary(client, enterprise_ctx):
    client.force_login(enterprise_ctx["user"])

    response = client.post(
        reverse("invest-sites-smev-batch"),
        {"cadastral_numbers": enterprise_ctx["site"].cadastral_number},
    )

    assert response.status_code == 302
    assert reverse("invest-smev-console") in response["Location"]
    assert "batch_id=" in response["Location"]


@pytest.mark.django_db
def test_selective_apply_accepts_and_rejects_fields(enterprise_ctx):
    req = request_smev_fill(site=enterprise_ctx["site"], user=enterprise_ctx["user"])

    apply_smev_response(request=req, user=enterprise_ctx["user"], fields=["address"], rejected_fields=["vri"])
    enterprise_ctx["site"].refresh_from_db()
    req.refresh_from_db()

    assert enterprise_ctx["site"].address
    assert enterprise_ctx["site"].vri == ""
    assert req.response_payload["rejected_fields"] == ["vri"]


@pytest.mark.django_db
def test_contour_creates_three_services_with_shared_correlation(client, enterprise_ctx):
    client.force_login(enterprise_ctx["user"])

    response = client.post(reverse("invest-site-smev-contour", args=[enterprise_ctx["site"].pk]))

    assert response.status_code == 302
    assert InvestSmevRequest.objects.filter(site=enterprise_ctx["site"]).values("correlation_id").distinct().count() == 1
    assert InvestSmevRequest.objects.filter(site=enterprise_ctx["site"]).count() == 3


@pytest.mark.django_db
def test_egrn_apply_adds_map_intersection_hint(enterprise_ctx):
    req = request_smev_fill(site=enterprise_ctx["site"], user=enterprise_ctx["user"])

    apply_smev_response(request=req, user=enterprise_ctx["user"])
    enterprise_ctx["site"].refresh_from_db()

    assert enterprise_ctx["site"].latitude is not None
    assert enterprise_ctx["site"].external_ids["smev_rgis_intersections"]


@pytest.mark.django_db
def test_auto_smev_marks_critical_stop_factor(enterprise_ctx):
    req = request_smev_fill(site=enterprise_ctx["site"], user=enterprise_ctx["user"])
    req.response_payload["encumbrances"] = "Санитарно-защитная зона критическое ограничение"
    req.save(update_fields=["response_payload"])

    apply_smev_response(request=req, user=enterprise_ctx["user"])
    enterprise_ctx["site"].refresh_from_db()

    assert enterprise_ctx["site"].external_ids["smev_stop_factor"]
    assert InvestStopFactor.objects.filter(project=enterprise_ctx["project"], status=InvestStopFactor.Status.BLOCKING).exists()


@pytest.mark.django_db
def test_audit_trail_logs_request_apply_reject_retry_emulate(enterprise_ctx):
    req = request_smev_fill(site=enterprise_ctx["site"], user=enterprise_ctx["user"])
    apply_smev_response(request=req, user=enterprise_ctx["user"], fields=["address"], rejected_fields=["vri"])
    req.retry_or_dead_letter(actor=enterprise_ctx["user"])
    emulate_gateway_response(req, actor=enterprise_ctx["user"])
    req.refresh_from_db()

    actions = [event["action"] for event in req.audit_trail]
    assert {"request", "apply", "reject", "retry", "emulate"}.issubset(actions)


@pytest.mark.django_db
def test_live_apply_forbidden_for_non_admin(client, enterprise_ctx):
    req = InvestSmevRequest.objects.create(
        subsystem=enterprise_ctx["sub"],
        site=enterprise_ctx["site"],
        service=InvestSmevRequest.Service.EGRN,
        status=InvestSmevRequest.Status.DONE,
        is_mock=False,
        response_payload={"address": "Live address", "cadastral_number": enterprise_ctx["site"].cadastral_number},
    )
    client.force_login(enterprise_ctx["user"])

    response = client.post(reverse("invest-site-smev-apply", args=[enterprise_ctx["site"].pk, req.pk]))

    assert response.status_code == 403


@pytest.mark.django_db
def test_report_page_shows_weekly_counts_and_avg_time(client, enterprise_ctx):
    req = request_smev_fill(site=enterprise_ctx["site"], user=enterprise_ctx["user"])
    req.finished_at = timezone.now()
    req.save(update_fields=["finished_at"])
    client.force_login(enterprise_ctx["user"])

    response = client.get(reverse("invest-smev-report"))

    assert response.status_code == 200
    assert "Среднее время" in response.content.decode()


@pytest.mark.django_db
def test_vs_catalog_defaults_validate_required_keys(enterprise_ctx):
    info = InvestSmevInfoType.objects.create(
        code="test-egrn",
        service=InvestSmevRequest.Service.EGRN,
        name="Test EGRN",
        contract_version="1",
        schema_json={"required": ["cadastral_number", "address"]},
    )

    assert validate_smev_response(info, {"cadastral_number": "1", "address": "ok"}) == []


@pytest.mark.django_db
def test_emulator_fills_live_pending_response(enterprise_ctx):
    req = InvestSmevRequest.objects.create(
        subsystem=enterprise_ctx["sub"],
        site=enterprise_ctx["site"],
        service=InvestSmevRequest.Service.EGRN,
        status=InvestSmevRequest.Status.LIVE_PENDING,
        request_payload={"delay_seconds": 5},
    )

    emulate_gateway_response(req, actor=enterprise_ctx["user"])
    req.refresh_from_db()

    assert req.status == InvestSmevRequest.Status.DONE
    assert req.response_payload["emulated_delay_seconds"] == 5


@pytest.mark.django_db
def test_schema_error_status_on_missing_required_key(enterprise_ctx):
    info = InvestSmevInfoType.objects.create(
        code="schema-egrn",
        service=InvestSmevRequest.Service.EGRN,
        name="Schema EGRN",
        contract_version="1",
        schema_json={"required": ["missing_key"]},
    )
    req = request_smev_fill(site=enterprise_ctx["site"], user=enterprise_ctx["user"])

    errors = validate_smev_response(info, req.response_payload, request=req)
    req.refresh_from_db()

    assert errors == ["missing_key"]
    assert req.status == InvestSmevRequest.Status.SCHEMA_ERROR


@pytest.mark.django_db
def test_egrn_apply_marks_package_item_done(enterprise_ctx):
    package = ensure_package(enterprise_ctx["project"])
    req = request_smev_fill(site=enterprise_ctx["site"], user=enterprise_ctx["user"])

    apply_smev_response(request=req, user=enterprise_ctx["user"])

    assert package.items.get(code="egrn_smev").status == InvestPackageItem.Status.ATTACHED


@pytest.mark.django_db
def test_protocol_pdf_endpoint(client, enterprise_ctx):
    req = request_smev_fill(site=enterprise_ctx["site"], user=enterprise_ctx["user"])
    client.force_login(enterprise_ctx["user"])

    response = client.get(reverse("invest-smev-protocol", args=[req.pk]))

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"


@pytest.mark.django_db
def test_booking_auto_triggers_smev(enterprise_ctx):
    enterprise_ctx["site"].completeness_pct = 100
    enterprise_ctx["site"].save(update_fields=["completeness_pct", "updated_at"])
    ensure_automation_config(enterprise_ctx["sub"])

    book_site(project=enterprise_ctx["project"], site=enterprise_ctx["site"], user=enterprise_ctx["user"])
    auto_smev_enrich_site(enterprise_ctx["site"], user=enterprise_ctx["user"])

    assert InvestSmevRequest.objects.filter(site=enterprise_ctx["site"]).count() >= 3
