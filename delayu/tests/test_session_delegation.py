from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

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
    UserSession,
)
from delayu.services.case_acl import user_can_view_case
from delayu.services.delegation import create_delegation, delegation_principals
from delayu.services.retention import retention_alerts
from delayu.services.session_registry import list_user_sessions

User = get_user_model()


@pytest.fixture
def sec_ctx(db):
    sub = Subsystem.objects.create(code="sec2", name="Sec2", industry_template="core")
    org = Organization.objects.create(subsystem=sub, code="o1", name="Org")
    role = Role.objects.create(subsystem=sub, code="user", name="User")
    mod, _ = ModuleCatalog.objects.get_or_create(code="M07", defaults={"name": "Cabinet", "group": "work"})
    RoleModulePermission.objects.create(role=role, module=mod, can_view=True)
    SubsystemModule.objects.create(subsystem=sub, module=mod, enabled=True)
    boss = User.objects.create_user("boss", password="x")
    deputy = User.objects.create_user("deputy", password="x")
    for u in (boss, deputy):
        SubsystemMembership.objects.create(user=u, subsystem=sub, organization=org, role=role, is_default=True)
        p, _ = UserProfile.objects.get_or_create(user=u)
        p.active_subsystem = sub
        p.totp_secret = "JBSWY3DPEHPK3PXP"
        p.two_factor_enabled = True
        p.save()
    return sub, org, boss, deputy


@pytest.mark.django_db
def test_session_registry_list(sec_ctx):
    _sub, _org, boss, _deputy = sec_ctx
    UserSession.objects.create(
        user=boss,
        session_key="abc123sessionkeyfortest0001",
        ip_address="127.0.0.1",
        user_agent="Mozilla/5.0 Chrome/120.0",
    )
    rows = list_user_sessions(boss, current_key="abc123sessionkeyfortest0001")
    assert len(rows) == 1
    assert rows[0]["is_current"]
    assert "Chrome" in rows[0]["label"]


@pytest.mark.django_db
def test_delegation_case_access(sec_ctx):
    sub, org, boss, deputy = sec_ctx
    today = timezone.now().date()
    create_delegation(
        subsystem=sub,
        from_user=boss,
        to_user=deputy,
        start_at=today,
        end_at=today,
    )
    assert delegation_principals(deputy, sub) == [boss.pk]
    case = CaseFile.objects.create(
        subsystem=sub,
        organization=org,
        number="D-001",
        title="Boss case",
        assignee=boss,
        created_by=boss,
    )
    assert user_can_view_case(deputy, case)


@pytest.mark.django_db
def test_retention_alerts(sec_ctx):
    sub, org, boss, _deputy = sec_ctx
    today = timezone.now().date()
    CaseFile.objects.create(
        subsystem=sub,
        organization=org,
        number="A-001",
        title="Archive",
        created_by=boss,
        is_archived=True,
        archived_at=timezone.now(),
        retention_until=today + timedelta(days=10),
    )
    alerts = retention_alerts(sub)
    assert len(alerts) == 1
