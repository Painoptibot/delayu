import pytest
from django.contrib.auth import get_user_model

from delayu.models import (
    CaseFile,
    Correspondence,
    ModuleCatalog,
    NSIClassifier,
    Organization,
    Role,
    RoleModulePermission,
    Subsystem,
    SubsystemMembership,
    SubsystemModule,
    UserProfile,
)
from delayu.services.access import user_can
from delayu.services.nsi_choices import sync_classifiers_for_subsystem
from delayu.services.numbering import next_reg_number
from delayu.services.object_registry import global_search
from delayu.services.privacy import mask_value, user_may_view_pii

User = get_user_model()


@pytest.mark.django_db
def test_nsi_sync_creates_classifiers():
    sub = Subsystem.objects.create(code="testsub", name="Test")
    sync_classifiers_for_subsystem(sub)
    assert NSIClassifier.objects.filter(subsystem=sub).count() >= 10


@pytest.mark.django_db
def test_reg_number_increments():
    user = User.objects.create_user("numuser", password="x")
    sub = Subsystem.objects.create(code="numsub", name="Num")
    org = Organization.objects.create(subsystem=sub, code="o1", name="Org")
    n1 = next_reg_number(sub, Correspondence.Direction.IN)
    Correspondence.objects.create(
        subsystem=sub,
        direction=Correspondence.Direction.IN,
        reg_number=n1,
        reg_date="2026-01-01",
        subject="t",
        created_by=user,
    )
    n2 = next_reg_number(sub, Correspondence.Direction.IN)
    assert n1 != n2


@pytest.mark.django_db
def test_global_search_finds_case():
    user = User.objects.create_user("u1", password="x")
    sub = Subsystem.objects.create(code="srch", name="S")
    org = Organization.objects.create(subsystem=sub, code="o1", name="Org")
    CaseFile.objects.create(
        subsystem=sub,
        organization=org,
        number="CASE-001",
        title="UniqueAlphaTitle",
        created_by=user,
    )
    hits = global_search(sub, "UniqueAlpha")
    assert any(h["type"] == "case" for h in hits)


def test_mask_value():
    assert "•" in mask_value("secret", 0)


@pytest.mark.django_db
def test_view_pii_permission():
    user = User.objects.create_user("piiuser", password="x")
    sub = Subsystem.objects.create(code="pii", name="P")
    org = Organization.objects.create(subsystem=sub, code="org", name="O")
    role = Role.objects.create(subsystem=sub, code="hr", name="HR")
    mod = ModuleCatalog.objects.create(code="M03", name="Users", group="admin")
    RoleModulePermission.objects.create(
        role=role, module=mod, can_view=True, can_view_pii=True
    )
    SubsystemMembership.objects.create(user=user, subsystem=sub, organization=org, role=role)
    SubsystemModule.objects.create(subsystem=sub, module=mod, enabled=True)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.active_subsystem = sub
    profile.save()
    assert user_can(user, "M03", "view_pii")


@pytest.mark.django_db
def test_api_health(client):
    r = client.get("/api/v1/health/")
    assert r.status_code == 200
    assert r.json()["platform"] == "ДелаЮ"


@pytest.mark.django_db
def test_openapi_contract(client, django_user_model):
    user = django_user_model.objects.create_superuser("api", "a@b.c", "x")
    client.force_login(user)
    r = client.get("/api/v1/openapi.json")
    assert r.status_code == 200
    assert "paths" in r.json()
