"""F7 — автоматический smoke по docs/acceptance-50.md."""
import json
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from delayu.models import CaseFile, SsoProvider, Subsystem
from delayu.services.integrations import create_api_key
from delayu.services.openapi_contract import build_openapi_spec
from delayu.services.registry_platform import build_product_passport, seed_registry_catalog

User = get_user_model()

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def pilot_env(db):
    call_command("seed_catalog", verbosity=0)
    call_command("seed_demo", verbosity=0)
    seed_registry_catalog()
    sub = Subsystem.objects.get(code="pilot")
    admin = User.objects.get(username="admin")
    case = CaseFile.objects.filter(subsystem=sub).first()
    assert case is not None
    client = Client()
    client.force_login(admin)
    return {"sub": sub, "admin": admin, "case": case, "client": client}


def _assert_ok(resp, path: str):
    assert resp.status_code in (200, 302), f"{path} -> {resp.status_code}"


def _smoke_get(client, path: str):
    resp = client.get(path)
    if resp.status_code == 405:
        return
    _assert_ok(resp, path)


@pytest.mark.django_db(transaction=True)
def test_acceptance_50_smoke_pages(pilot_env):
    """#1–#50 — ключевые UI-маршруты открываются для admin/pilot."""
    client = pilot_env["client"]
    case = pilot_env["case"]
    case_pk = case.pk

    static_pages = [
        "/exploit/product-passport/",
        "/exploit/product-passport/export/",
        "/acceptance/",
        "/exploit/pii/",
        "/ai/",
        "/ai/tools/",
        "/ai/hitl/",
        "/ai/feedback/",
        "/administration/audit/",
        "/administration/audit/snapshot/",
        "/workspace/cabinet/access/",
        "/workspace/cabinet/security/",
        "/auth/reauth/",
        "/auth/2fa/verify/",
        "/ops/case-kinds/",
        "/ops/forms/",
        "/ops/nsi/",
        "/studio/bpm/",
        "/bpm/sla/monitor/",
        "/workspace/today/",
        "/workspace/favorites/",
        "/cases/",
        f"/cases/{case_pk}/",
        f"/cases/{case_pk}/?tab=links",
        f"/cases/{case_pk}/?tab=documents",
        "/cases/new/",
        "/analytics/reports/",
        "/infra/etl/",
        "/integrations/messages/",
        "/correspondence/inbound/new/",
        "/correspondence/print-templates/",
        "/correspondence/signatures/",
        "/exploit/mail/delivery/",
        "/platform/search/",
        "/platform/onboarding/",
    ]
    post_only = {"/ai/feedback/"}
    for path in static_pages:
        if path in post_only:
            continue
        _smoke_get(client, path)

    resp = client.post("/ai/feedback/", data={"rating": "5", "comment": "acceptance smoke"})
    assert resp.status_code in (200, 302, 201)


@pytest.mark.django_db(transaction=True)
def test_acceptance_50_api_and_services(pilot_env):
    """#4, #8, #10, #11, #38, #41, #46 — API и сервисные сценарии."""
    client = pilot_env["client"]
    sub = pilot_env["sub"]

    passport = build_product_passport(sub)
    assert passport["modules_count"] >= 10
    assert passport["compliance_rows"] is not None

    spec = build_openapi_spec()
    assert "/api/v1/ai/policy/" in spec["paths"]

    _obj, raw = create_api_key(subsystem=sub, name="acceptance", rate_limit=100)
    resp = client.get("/api/v1/cases/", HTTP_AUTHORIZATION=f"Bearer {raw}")
    assert resp.status_code == 200
    payload = resp.json()
    assert "results" in payload or isinstance(payload, list)

    resp = client.patch(
        "/api/v1/ai/policy/",
        data=json.dumps({"max_requests_per_day": 99}),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {raw}",
    )
    assert resp.status_code == 200
    assert resp.json()["max_requests_per_day"] == 99

    resp = client.get("/api/v1/openapi.json")
    assert resp.status_code == 200
    assert "ai/policy" in resp.content.decode()

    resp = client.post("/platform/privacy-mode/", data={"enabled": "1"})
    assert resp.status_code == 200
    assert resp.json()["privacy_mode"] is True

    resp = client.post(
        reverse("platform-today-widgets-save"),
        data={"widgets": json.dumps(["kpi", "tasks"])},
    )
    assert resp.status_code in (200, 302)

    provider = SsoProvider.objects.filter(subsystem=sub).first()
    if provider:
        _assert_ok(client.get(f"/auth/sso/{provider.pk}/start/"), "sso-start")


@pytest.mark.django_db(transaction=True)
def test_acceptance_50_assets_and_rbac(pilot_env):
    """#3, #48, #49 — статические ресурсы и RBAC."""
    from delayu.models import ModuleCatalog, Organization, Role, RoleModulePermission, SubsystemMembership, SubsystemModule

    sub = pilot_env["sub"]
    org = Organization.objects.filter(subsystem=sub).first()
    role = Role.objects.create(subsystem=sub, code="no_cases", name="No cases")
    mod_admin, _ = ModuleCatalog.objects.get_or_create(code="M01", defaults={"name": "Админ", "group": "core"})
    for mod in (mod_admin,):
        RoleModulePermission.objects.create(role=role, module=mod, can_view=True)
        SubsystemModule.objects.get_or_create(subsystem=sub, module=mod, defaults={"enabled": True})
    limited = User.objects.create_user("limited_accept", password="x")
    SubsystemMembership.objects.create(
        user=limited, subsystem=sub, organization=org, role=role, is_default=True
    )
    limited_client = Client()
    limited_client.force_login(limited)

    mobile_css = PROJECT_ROOT / "src" / "assets" / "css" / "delayu-mobile.css"
    a11y_css = PROJECT_ROOT / "src" / "assets" / "css" / "delayu-a11y.css"
    assert mobile_css.is_file()
    assert a11y_css.is_file()
    assert "@media" in mobile_css.read_text(encoding="utf-8")

    resp = limited_client.get("/cases/")
    assert resp.status_code in (403, 200)
    if resp.status_code == 200:
        assert "not-authorized" in resp.content.decode().lower() or "403" in resp.content.decode()

    resp = pilot_env["client"].get("/")
    assert resp.status_code == 200
    content = resp.content.decode()
    assert "main-content" in content or 'id="main-content"' in content
