import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from delayu.models import (
    ActivityEvent,
    AuditLog,
    CaseFile,
    Comment,
    ModuleCatalog,
    Organization,
    Role,
    RoleModulePermission,
    Subsystem,
    SubsystemMembership,
    SubsystemModule,
)
from delayu.models_business import AppendOnlyError
from delayu.services import audit
from delayu.services.case_360 import build_case_360_context, build_case_timeline

User = get_user_model()


@pytest.fixture
def platform_sub(db):
    sub = Subsystem.objects.create(code="plat360", name="360 test", industry_template="core")
    org = Organization.objects.create(subsystem=sub, code="o1", name="Org")
    role = Role.objects.create(subsystem=sub, code="admin", name="Admin")
    for code, name in [("M01", "Админ"), ("M22", "Дела")]:
        mod, _ = ModuleCatalog.objects.get_or_create(code=code, defaults={"name": name, "group": "core"})
        RoleModulePermission.objects.create(role=role, module=mod, can_view=True, can_change=True)
        SubsystemModule.objects.create(subsystem=sub, module=mod, enabled=True)
    user = User.objects.create_user("plat_user", password="x")
    SubsystemMembership.objects.create(
        user=user, subsystem=sub, organization=org, role=role, is_default=True
    )
    return sub, user, org


@pytest.mark.django_db
def test_audit_log_append_only(platform_sub):
    sub, user, _org = platform_sub
    audit.log_action(user, sub, "create", "CaseFile", 1, payload={"email": "a@b.c"})
    entry = AuditLog.objects.get(subsystem=sub)
    with pytest.raises(AppendOnlyError):
        entry.action = "hack"
        entry.save()
    with pytest.raises(AppendOnlyError):
        entry.delete()
    with pytest.raises(AppendOnlyError):
        AuditLog.objects.filter(pk=entry.pk).delete()


@pytest.mark.django_db
def test_export_audit_csv(platform_sub):
    sub, user, _org = platform_sub

    class FakeRequest:
        META = {"REMOTE_ADDR": "10.0.0.5"}

    audit.log_action(
        user,
        sub,
        "update",
        "CaseFile",
        5,
        payload={"phone": "+7999", "email": "a@b.c"},
        request=FakeRequest(),
    )

    resp = audit.export_audit_csv(sub, mask_pii=True)
    body = resp.content.decode("utf-8-sig")
    assert "update" in body
    assert "10.0.0.xxx" in body
    assert "***" in body


@pytest.mark.django_db
def test_build_case_timeline(platform_sub):
    sub, user, org = platform_sub
    case = CaseFile.objects.create(
        subsystem=sub,
        organization=org,
        number="P360-2026-0001",
        title="Test",
        created_by=user,
    )
    audit.log_action(user, sub, "create", "CaseFile", case.pk)
    Comment.objects.create(subsystem=sub, case=case, author=user, body="Note")
    ActivityEvent.objects.create(
        subsystem=sub,
        actor=user,
        verb="изменил дело",
        target_repr=case.number,
        module_code="M22",
        link_path=f"/cases/{case.pk}/",
    )
    timeline = build_case_timeline(case)
    kinds = {e["kind"] for e in timeline}
    assert "audit" in kinds
    assert "comment" in kinds
    assert "activity" in kinds
    ctx = build_case_360_context(case)
    assert ctx["stats"]["comments"] == 1
    assert len(ctx["timeline"]) >= 3


@pytest.mark.django_db
def test_case_detail_360_tabs(client, platform_sub):
    sub, user, org = platform_sub
    from delayu.models import UserProfile

    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.active_subsystem = sub
    from delayu.services.totp import generate_secret

    profile.totp_secret = generate_secret()
    profile.two_factor_enabled = True
    profile.save()
    case = CaseFile.objects.create(
        subsystem=sub,
        organization=org,
        number="P360-2026-0002",
        title="Tab test",
        created_by=user,
    )
    client.force_login(user)
    session = client.session
    session["2fa_verified"] = True
    session.save()
    url = reverse("platform-case-detail", kwargs={"pk": case.pk})
    resp = client.get(f"{url}?tab=history")
    assert resp.status_code == 200
    assert "Хронология 360" in resp.content.decode()
