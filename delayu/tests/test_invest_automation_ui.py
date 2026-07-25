# delayu/tests/test_invest_automation_ui.py
import pytest
from django.contrib.auth import get_user_model

from delayu.models import ModuleCatalog, Organization, Role, RoleModulePermission, Subsystem, SubsystemMembership, SubsystemModule
from delayu.services.invest_automation_access import user_can_manage_invest_automation
from delayu.services.invest_roles import perm_for_role

User = get_user_model()


@pytest.fixture
def invest_roles_ctx(db):
    sub = Subsystem.objects.create(
        code="inv-ui", name="Invest UI", industry_template="invest", status="active"
    )
    module = ModuleCatalog.objects.create(code="M22", name="Инвестпроекты")
    SubsystemModule.objects.create(subsystem=sub, module=module, enabled=True)
    org = Organization.objects.create(subsystem=sub, code="dept", name="Dept")
    roles = {}
    for code, name in [
        ("invest_admin", "Admin"),
        ("invest_agency", "Agency"),
    ]:
        role = Role.objects.create(subsystem=sub, code=code, name=name)
        RoleModulePermission.objects.create(role=role, module=module, **perm_for_role(code, "M22"))
        roles[code] = role
    return {"sub": sub, "org": org, "roles": roles, "module": module}


def _member(ctx, username, role_code, *, platform_admin=False):
    user = User.objects.create_user(username, password="x")
    if platform_admin:
        from delayu.models_business import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.is_platform_admin = True
        profile.save(update_fields=["is_platform_admin"])
    membership = SubsystemMembership.objects.create(
        user=user,
        subsystem=ctx["sub"],
        organization=ctx["org"],
        role=ctx["roles"][role_code],
        is_default=True,
    )
    return user, membership


@pytest.mark.django_db
def test_access_invest_admin_allowed(invest_roles_ctx):
    user, membership = _member(invest_roles_ctx, "adm", "invest_admin")
    assert user_can_manage_invest_automation(user, membership) is True


@pytest.mark.django_db
def test_access_agency_denied(invest_roles_ctx):
    user, membership = _member(invest_roles_ctx, "ag", "invest_agency")
    assert user_can_manage_invest_automation(user, membership) is False


@pytest.mark.django_db
def test_access_platform_admin_allowed(invest_roles_ctx):
    user, membership = _member(invest_roles_ctx, "padm", "invest_agency", platform_admin=True)
    assert user_can_manage_invest_automation(user, membership) is True


@pytest.mark.django_db
def test_access_superuser_allowed(invest_roles_ctx):
    user, membership = _member(invest_roles_ctx, "su", "invest_agency")
    user.is_superuser = True
    user.save(update_fields=["is_superuser"])
    assert user_can_manage_invest_automation(user, membership) is True
