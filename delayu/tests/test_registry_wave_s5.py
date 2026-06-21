"""#35, #38, #41, #46, #49 — волна S5."""
import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from delayu.models import CaseFile, UserProfile
from delayu.services.ai import get_or_create_policy, serialize_ai_policy, update_ai_policy
from delayu.services.correspondence import register_inbound_enhanced
from delayu.services.integrations import create_api_key
from delayu.services.openapi_contract import build_openapi_spec
from delayu.services import studio

User = get_user_model()


@pytest.fixture
def s5_sub(db):
    from delayu.models import ModuleCatalog, Organization, Role, RoleModulePermission, Subsystem, SubsystemMembership, SubsystemModule

    sub = Subsystem.objects.create(code="s5wave", name="S5", industry_template="core", status="active")
    org = Organization.objects.create(subsystem=sub, code="o1", name="Org")
    role = Role.objects.create(subsystem=sub, code="specialist", name="Spec")
    for code in ["M24", "M43", "M66", "M08"]:
        mod, _ = ModuleCatalog.objects.get_or_create(code=code, defaults={"name": code, "group": "core"})
        RoleModulePermission.objects.create(
            role=role, module=mod, can_view=True, can_create=True, can_change=True
        )
        SubsystemModule.objects.create(subsystem=sub, module=mod, enabled=True)
    user = User.objects.create_user("s5_user", password="secret")
    SubsystemMembership.objects.create(user=user, subsystem=sub, organization=org, role=role, is_default=True)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.active_subsystem = sub
    profile.save()
    return sub, user, org


@pytest.mark.django_db
def test_openapi_s5_paths():
    spec = build_openapi_spec()
    paths = spec["paths"]
    assert "/api/v1/ai/policy/" in paths
    assert "patch" in paths["/api/v1/ai/policy/"]
    assert "/api/v1/integration/messages/" in paths
    assert "/api/v1/notifications/delivery/" in paths
    assert "AiPolicy" in spec["components"]["schemas"]


@pytest.mark.django_db
def test_ai_policy_api_get_patch(s5_sub):
    sub, _user, _org = s5_sub
    _obj, raw = create_api_key(subsystem=sub, name="s5", rate_limit=50)
    client = Client()
    resp = client.get("/api/v1/ai/policy/", HTTP_AUTHORIZATION=f"Bearer {raw}")
    assert resp.status_code == 200
    assert "model_name" in resp.json()

    resp = client.patch(
        "/api/v1/ai/policy/",
        data=json.dumps({"max_requests_per_day": 120, "allow_pii": True}),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {raw}",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["max_requests_per_day"] == 120
    assert data["allow_pii"] is True


@pytest.mark.django_db
def test_ai_policy_service(s5_sub):
    sub, _user, _org = s5_sub
    policy = get_or_create_policy(sub)
    data = update_ai_policy(policy, {"notes": "test policy", "model_name": "demo-v2"})
    assert data["notes"] == "test policy"
    assert serialize_ai_policy(policy)["model_name"] == "demo-v2"


@pytest.mark.django_db
def test_register_inbound_with_new_case(s5_sub):
    sub, user, org = s5_sub
    corr, case, hint = register_inbound_enhanced(
        subsystem=sub,
        organization=org,
        user=user,
        subject="Жалоба на отопление",
        counterparty="Иванов",
        create_case=True,
        new_case_title="Жалоба УК",
    )
    assert corr.pk
    assert case is not None
    assert case.title == "Жалоба УК"
    assert corr.case_id == case.pk
    assert hint["theme"] == "Жалоба"


@pytest.mark.django_db
def test_inbound_classify_preview(s5_sub):
    sub, user, _org = s5_sub
    client = Client()
    client.force_login(user)
    resp = client.get("/correspondence/inbound/classify-preview/?subject=Заявление+на+ремонт")
    assert resp.status_code == 200
    assert resp.json()["theme"] == "Заявление"


@pytest.mark.django_db
def test_today_widgets_save(s5_sub):
    sub, user, _org = s5_sub
    profile, _ = UserProfile.objects.get_or_create(user=user)
    saved = studio.save_today_widgets(profile, ["kpi_overdue", "tasks_table"])
    assert saved == ["kpi_overdue", "tasks_table"]
    assert studio.today_widgets_for_profile(profile) == ["kpi_overdue", "tasks_table"]

    client = Client()
    client.force_login(user)
    resp = client.post(
        "/workspace/today/widgets/",
        data={"widgets": ["quick_inbox", "kpi_today"]},
    )
    assert resp.status_code == 302
    profile.refresh_from_db()
    assert studio.today_widgets_for_profile(profile) == ["quick_inbox", "kpi_today"]


@pytest.mark.django_db
def test_inbound_register_view_permission(db):
    from delayu.models import ModuleCatalog, Organization, Role, RoleModulePermission, Subsystem, SubsystemMembership, SubsystemModule

    sub = Subsystem.objects.create(code="perm", name="P", industry_template="core")
    org = Organization.objects.create(subsystem=sub, code="o1", name="Org")
    role = Role.objects.create(subsystem=sub, code="manager", name="Mgr")
    mod, _ = ModuleCatalog.objects.get_or_create(code="M24", defaults={"name": "In", "group": "docs"})
    RoleModulePermission.objects.create(role=role, module=mod, can_view=True, can_create=False)
    SubsystemModule.objects.create(subsystem=sub, module=mod, enabled=True)
    user = User.objects.create_user("mgr_only", password="x")
    SubsystemMembership.objects.create(user=user, subsystem=sub, organization=org, role=role, is_default=True)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.active_subsystem = sub
    profile.save()

    client = Client()
    client.force_login(user)
    assert client.get("/correspondence/inbound/new/").status_code == 200
    assert client.get("/correspondence/inbound/classify-preview/?subject=test").status_code == 200
