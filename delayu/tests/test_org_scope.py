"""#10 — org scope на реестре дел и API."""
import pytest
from django.contrib.auth import get_user_model

from delayu.models import CaseFile, Organization, Role, RoleModulePermission, Subsystem, SubsystemMembership, SubsystemModule
from delayu.models import ModuleCatalog
from delayu.services.cases import filter_cases
from delayu.services.integrations import create_api_key

User = get_user_model()


@pytest.fixture
def org_scope_sub(db):
    sub = Subsystem.objects.create(code="orgscope", name="Org", industry_template="core")
    org_a = Organization.objects.create(subsystem=sub, code="a", name="Org A")
    org_b = Organization.objects.create(subsystem=sub, code="b", name="Org B")
    role = Role.objects.create(subsystem=sub, code="specialist", name="Spec")
    mod, _ = ModuleCatalog.objects.get_or_create(code="M22", defaults={"name": "Cases", "group": "cases"})
    mod43, _ = ModuleCatalog.objects.get_or_create(code="M43", defaults={"name": "API", "group": "int"})
    RoleModulePermission.objects.create(role=role, module=mod, can_view=True, can_change=False)
    RoleModulePermission.objects.create(role=role, module=mod43, can_view=True)
    SubsystemModule.objects.create(subsystem=sub, module=mod, enabled=True)
    SubsystemModule.objects.create(subsystem=sub, module=mod43, enabled=True)
    user_a = User.objects.create_user("user_a", password="x")
    user_b = User.objects.create_user("user_b", password="x")
    SubsystemMembership.objects.create(
        user=user_a, subsystem=sub, organization=org_a, role=role, is_default=True
    )
    SubsystemMembership.objects.create(
        user=user_b, subsystem=sub, organization=org_b, role=role, is_default=True
    )
    CaseFile.objects.create(
        subsystem=sub, organization=org_a, number="A-1", title="Case A", created_by=user_a
    )
    CaseFile.objects.create(
        subsystem=sub, organization=org_b, number="B-1", title="Case B", created_by=user_b
    )
    return sub, user_a, user_b, org_a, org_b


@pytest.mark.django_db
def test_filter_cases_org_scope(org_scope_sub):
    sub, user_a, user_b, _org_a, _org_b = org_scope_sub
    ids_a = set(filter_cases(sub, user_a, params={}, can_change_all=False).values_list("number", flat=True))
    ids_b = set(filter_cases(sub, user_b, params={}, can_change_all=False).values_list("number", flat=True))
    assert ids_a == {"A-1"}
    assert ids_b == {"B-1"}


@pytest.mark.django_db
def test_api_cases_org_scope(org_scope_sub):
    from django.test import Client

    sub, user_a, _user_b, _org_a, _org_b = org_scope_sub
    _obj, raw = create_api_key(subsystem=sub, name="org", rate_limit=100)
    client = Client()
    client.force_login(user_a)
    resp = client.get("/api/v1/cases/", HTTP_AUTHORIZATION=f"Bearer {raw}")
    assert resp.status_code == 200
    numbers = {r["number"] for r in resp.json()["results"]}
    assert numbers == {"A-1"}
