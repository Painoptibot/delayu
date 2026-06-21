"""#6, #15, #33, #40, #45 — волна реестра."""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from delayu.models import AiFeedback, BulkOperation, CaseFile, Organization, PiiMaskingPolicy
from delayu.services.ai import classify_correspondence
from delayu.services.demo_mode import blocks_mutation, subsystem_demo_enabled
from delayu.services.reauth import is_reauth_valid, mark_reauth

User = get_user_model()


@pytest.fixture
def registry_sub(db):
    from delayu.models import ModuleCatalog, Role, RoleModulePermission, Subsystem, SubsystemMembership, SubsystemModule

    sub = Subsystem.objects.create(code="regwave", name="Registry wave", industry_template="core")
    org = Organization.objects.create(subsystem=sub, code="o1", name="Org")
    role = Role.objects.create(subsystem=sub, code="specialist", name="Specialist")
    for code, name in [
        ("M01", "Админ"),
        ("M06", "Архив"),
        ("M22", "Дела"),
        ("M47", "ИИ"),
        ("M75", "Bulk"),
    ]:
        mod, _ = ModuleCatalog.objects.get_or_create(code=code, defaults={"name": name, "group": "core"})
        RoleModulePermission.objects.create(
            role=role, module=mod, can_view=True, can_change=True, can_delete=True
        )
        SubsystemModule.objects.create(subsystem=sub, module=mod, enabled=True)
    user = User.objects.create_user("reg_user", password="secret")
    SubsystemMembership.objects.create(
        user=user, subsystem=sub, organization=org, role=role, is_default=True
    )
    return sub, user, org


def _login_client(client, user, *, with_reauth: bool = False, password: str = "secret"):
    client.force_login(user)
    client.session.save()
    if with_reauth:
        resp = client.post(
            reverse("reauth-confirm"),
            {"password": password, "next": reverse("platform-cases")},
        )
        assert resp.status_code == 302
    return client


@pytest.mark.django_db
def test_classify_explainability():
    r = classify_correspondence("Жалоба на управляющую компанию")
    assert r["theme"] == "Жалоба"
    assert r["reasons"]
    assert 0 < r["confidence"] <= 1


@pytest.mark.django_db
def test_demo_mode_blocks_bulk_post(registry_sub, settings):
    settings.DELAYU_DEMO_MODE = True
    sub, user, org = registry_sub
    from django.test import RequestFactory

    req = RequestFactory().post("/cases/bulk/", {"case_ids": ["1"]})
    req.user = user
    req.session = {}
    assert blocks_mutation(req) is True


@pytest.mark.django_db
def test_subsystem_demo_policy(registry_sub):
    sub, _user, _org = registry_sub
    PiiMaskingPolicy.objects.create(subsystem=sub, demo_mode=True)
    assert subsystem_demo_enabled(sub) is True


@pytest.mark.django_db
def test_reauth_session():
    client = Client()
    user = User.objects.create_user("reauth_u", password="x")
    client.force_login(user)
    from django.test import RequestFactory

    req = RequestFactory().get("/")
    req.session = client.session
    req.user = user
    assert is_reauth_valid(req) is False
    mark_reauth(req)
    assert is_reauth_valid(req) is True


@pytest.mark.django_db
def test_cases_bulk_requires_reauth(registry_sub):
    sub, user, org = registry_sub
    case = CaseFile.objects.create(
        subsystem=sub, organization=org, number="RW-2", title="Bulk", created_by=user
    )
    client = Client()
    _login_client(client, user)
    resp = client.post(
        reverse("platform-cases-bulk"),
        {"case_ids": [case.pk], "bulk_action": "status", "new_status": CaseFile.Status.IN_PROGRESS},
    )
    assert resp.status_code == 302
    assert "reauth" in resp.url


@pytest.mark.django_db
def test_cases_bulk_with_reauth(registry_sub):
    sub, user, org = registry_sub
    case = CaseFile.objects.create(
        subsystem=sub,
        organization=org,
        number="RW-3",
        title="Bulk ok",
        created_by=user,
        status=CaseFile.Status.NEW,
    )
    client = Client()
    _login_client(client, user, with_reauth=True)
    resp = client.post(
        reverse("platform-cases-bulk"),
        {"case_ids": [case.pk], "bulk_action": "status", "new_status": CaseFile.Status.IN_PROGRESS},
    )
    assert resp.status_code == 302
    assert "reauth" not in resp.url
    case.refresh_from_db()
    assert case.status == CaseFile.Status.IN_PROGRESS
    assert BulkOperation.objects.filter(subsystem=sub).exists()


@pytest.mark.django_db
def test_ai_feedback_create(registry_sub):
    sub, user, org = registry_sub
    client = Client()
    _login_client(client, user)
    resp = client.post(
        reverse("platform-ai-feedback"),
        {"rating": 5, "comment": "ok", "module_code": "M49", "next": "/ai/"},
    )
    assert resp.status_code == 302
    assert AiFeedback.objects.filter(subsystem=sub, rating=5).exists()
