import hashlib

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client

from delayu.models import (
    CaseFile,
    ModuleCatalog,
    Organization,
    Role,
    RoleModulePermission,
    Subsystem,
    SubsystemMembership,
    SubsystemModule,
    UserProfile,
)
from delayu.services.api_gateway import verify_api_key
from delayu.services.integrations import create_api_key
from delayu.services.openapi_contract import build_openapi_spec
from delayu.services.search_index import rebuild_search_index, search_index

User = get_user_model()


@pytest.fixture
def api_sub(db):
    sub = Subsystem.objects.create(code="api_test", name="API", industry_template="core")
    org = Organization.objects.create(subsystem=sub, code="o1", name="Org")
    role = Role.objects.create(subsystem=sub, code="viewer", name="Viewer")
    mod43, _ = ModuleCatalog.objects.get_or_create(code="M43", defaults={"name": "API", "group": "int"})
    mod22, _ = ModuleCatalog.objects.get_or_create(code="M22", defaults={"name": "Cases", "group": "cases"})
    RoleModulePermission.objects.create(role=role, module=mod43, can_view=True)
    RoleModulePermission.objects.create(role=role, module=mod22, can_view=True)
    SubsystemModule.objects.create(subsystem=sub, module=mod43, enabled=True)
    SubsystemModule.objects.create(subsystem=sub, module=mod22, enabled=True)
    user = User.objects.create_user("api_user", password="x")
    SubsystemMembership.objects.create(user=user, subsystem=sub, organization=org, role=role, is_default=True)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.active_subsystem = sub
    profile.totp_secret = "JBSWY3DPEHPK3PXP"
    profile.two_factor_enabled = True
    profile.save()
    return sub, user


@pytest.mark.django_db
def test_openapi_contract_structure():
    spec = build_openapi_spec()
    assert spec["openapi"].startswith("3.0")
    assert "/api/v1/search/" in spec["paths"]
    assert "ApiKeyAuth" in spec["components"]["securitySchemes"]


@pytest.mark.django_db
def test_api_key_auth_cases(api_sub):
    sub, user = api_sub
    _obj, raw = create_api_key(subsystem=sub, name="test", rate_limit=10)
    cache.clear()
    assert verify_api_key(raw) is not None
    client = Client()
    resp = client.get("/api/v1/cases/", HTTP_AUTHORIZATION=f"Bearer {raw}")
    assert resp.status_code == 200
    assert "results" in resp.json()


@pytest.mark.django_db
def test_api_key_rate_limit(api_sub):
    sub, _user = api_sub
    _obj, raw = create_api_key(subsystem=sub, name="limited", rate_limit=2)
    cache.clear()
    client = Client()
    for _ in range(2):
        assert client.get("/api/v1/cases/", HTTP_AUTHORIZATION=f"Bearer {raw}").status_code == 200
    resp = client.get("/api/v1/cases/", HTTP_AUTHORIZATION=f"Bearer {raw}")
    assert resp.status_code == 429


@pytest.mark.django_db
def test_search_index_rebuild(api_sub):
    sub, user = api_sub
    org = Organization.objects.get(subsystem=sub)
    CaseFile.objects.create(
        subsystem=sub,
        organization=org,
        number="API-2026-0001",
        title="UniqueSearchToken",
        created_by=user,
    )
    stats = rebuild_search_index(sub)
    assert stats["case"] >= 1
    hits = search_index(sub, "UniqueSearch")
    assert hits and hits[0]["score"] >= 0.34


@pytest.mark.django_db
def test_api_health_extended(client):
    resp = client.get("/api/v1/health/")
    data = resp.json()
    assert data["platform"] == "ДелаЮ"
    assert "search_index" in data["checks"]
