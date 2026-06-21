"""#11, #21, #30 — волна S6."""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from delayu.models import CaseFile, NSIClassifier, Organization
from delayu.services.case_360 import build_case_link_graph
from delayu.services.privacy import user_may_view_pii

User = get_user_model()


@pytest.fixture
def s6_sub(db):
    from delayu.models import ModuleCatalog, Role, RoleModulePermission, Subsystem, SubsystemMembership, SubsystemModule

    sub = Subsystem.objects.create(code="s6wave", name="S6", industry_template="core")
    org = Organization.objects.create(subsystem=sub, code="o1", name="Org")
    role = Role.objects.create(subsystem=sub, code="specialist", name="Spec")
    for code in ["M22", "M73"]:
        mod, _ = ModuleCatalog.objects.get_or_create(code=code, defaults={"name": code, "group": "core"})
        RoleModulePermission.objects.create(role=role, module=mod, can_view=True, can_create=True)
        SubsystemModule.objects.create(subsystem=sub, module=mod, enabled=True)
    user = User.objects.create_user("s6_user", password="secret", is_superuser=True)
    SubsystemMembership.objects.create(user=user, subsystem=sub, organization=org, role=role, is_default=True)
    return sub, user, org


@pytest.mark.django_db
def test_privacy_mode_session(s6_sub):
    _sub, user, _org = s6_sub
    client = Client()
    client.force_login(user)
    assert user_may_view_pii(user) is True
    resp = client.post("/platform/privacy-mode/", data={"enabled": "1"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["privacy_mode"] is True
    assert data["allow_pii"] is False
    resp2 = client.get("/platform/privacy-mode/")
    assert resp2.json()["privacy_mode"] is True


@pytest.mark.django_db
def test_case_link_graph(s6_sub):
    sub, user, org = s6_sub
    case = CaseFile.objects.create(
        subsystem=sub, organization=org, number="S6-1", title="Link test", created_by=user
    )
    from delayu.models import Correspondence

    Correspondence.objects.create(
        subsystem=sub,
        direction=Correspondence.Direction.IN,
        reg_number="ВХ-S6-1",
        subject="Test",
        case=case,
        created_by=user,
    )
    graph = build_case_link_graph(case)
    assert graph["count"] >= 1
    assert any(n["type"] == "correspondence" for n in graph["nodes"])


@pytest.mark.django_db
def test_case_kinds_page(s6_sub):
    sub, user, _org = s6_sub
    from delayu.services.nsi_choices import sync_classifiers_for_subsystem

    sync_classifiers_for_subsystem(sub)
    assert NSIClassifier.objects.filter(subsystem=sub, code="case_kind").exists()
    client = Client()
    client.force_login(user)
    resp = client.get("/ops/case-kinds/")
    assert resp.status_code == 200
