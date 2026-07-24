import pytest
from django.contrib.auth import get_user_model

from delayu.models import Organization, Role, Subsystem, SubsystemMembership
from delayu.models_invest import InvestProject, InvestSite
from delayu.services.invest_roles import ROLE_SPECS, perm_for_role
from delayu.services.invest_scope import projects_for_membership, sites_for_membership

User = get_user_model()


@pytest.fixture
def scope_ctx(db):
    sub = Subsystem.objects.create(
        code="inv-scope", name="Scope", industry_template="invest", status="active"
    )
    org_a = Organization.objects.create(subsystem=sub, code="mo-a", name="МО А")
    org_b = Organization.objects.create(subsystem=sub, code="mo-b", name="МО Б")
    role_mo = Role.objects.create(subsystem=sub, code="invest_mo", name="МО")
    role_dept = Role.objects.create(subsystem=sub, code="invest_dept", name="Департамент")
    user_mo = User.objects.create_user("mo_u", password="x")
    user_dept = User.objects.create_user("dept_u", password="x")
    mem_mo = SubsystemMembership.objects.create(
        user=user_mo, subsystem=sub, organization=org_a, role=role_mo
    )
    mem_dept = SubsystemMembership.objects.create(
        user=user_dept, subsystem=sub, organization=org_a, role=role_dept
    )
    proj_a = InvestProject.objects.create(
        subsystem=sub, organization=org_a, code="P-A", name="Проект А",
        funnel=InvestProject.Funnel.ATTRACTION, stage="lead",
    )
    proj_b = InvestProject.objects.create(
        subsystem=sub, organization=org_b, code="P-B", name="Проект Б",
        funnel=InvestProject.Funnel.ATTRACTION, stage="lead",
    )
    site_a = InvestSite.objects.create(
        subsystem=sub, organization=org_a, cadastral_number="23:00:0000001:1", name="ЗУ А",
    )
    site_b = InvestSite.objects.create(
        subsystem=sub, organization=org_b, cadastral_number="23:00:0000002:1", name="ЗУ Б",
    )
    return {
        "sub": sub,
        "org_a": org_a,
        "org_b": org_b,
        "mem_mo": mem_mo,
        "mem_dept": mem_dept,
        "proj_a": proj_a,
        "proj_b": proj_b,
        "site_a": site_a,
        "site_b": site_b,
    }


@pytest.mark.django_db
def test_mo_sees_only_own_org_projects(scope_ctx):
    qs = projects_for_membership(scope_ctx["mem_mo"])
    assert set(qs) == {scope_ctx["proj_a"]}


@pytest.mark.django_db
def test_dept_sees_all_subsystem_projects(scope_ctx):
    qs = projects_for_membership(scope_ctx["mem_dept"])
    assert set(qs) == {scope_ctx["proj_a"], scope_ctx["proj_b"]}


@pytest.mark.django_db
def test_mo_sees_only_own_org_sites(scope_ctx):
    qs = sites_for_membership(scope_ctx["mem_mo"])
    assert set(qs) == {scope_ctx["site_a"]}


@pytest.mark.django_db
def test_dept_sees_all_subsystem_sites(scope_ctx):
    qs = sites_for_membership(scope_ctx["mem_dept"])
    assert set(qs) == {scope_ctx["site_a"], scope_ctx["site_b"]}


@pytest.mark.django_db
def test_unknown_role_sees_nothing(scope_ctx):
    role = Role.objects.create(subsystem=scope_ctx["sub"], code="other", name="Other")
    user = User.objects.create_user("other_u", password="x")
    mem = SubsystemMembership.objects.create(
        user=user,
        subsystem=scope_ctx["sub"],
        organization=scope_ctx["org_a"],
        role=role,
    )
    assert projects_for_membership(mem).count() == 0
    assert sites_for_membership(mem).count() == 0


def test_role_specs_has_five_invest_roles():
    assert set(ROLE_SPECS) == {
        "invest_admin",
        "invest_agency",
        "invest_dept",
        "invest_mo",
        "invest_viewer",
    }


def test_invest_admin_full_access_m22():
    p = perm_for_role("invest_admin", "M22")
    assert p == {
        "can_view": True,
        "can_create": True,
        "can_change": True,
        "can_delete": True,
    }


def test_invest_viewer_read_only():
    p = perm_for_role("invest_viewer", "M22")
    assert p["can_view"] is True
    assert p["can_create"] is False
    assert p["can_change"] is False
    assert p["can_delete"] is False


def test_invest_mo_can_create():
    p = perm_for_role("invest_mo", "M22")
    assert p["can_view"] is True
    assert p["can_create"] is True
    assert p["can_change"] is True


def test_perm_unknown_module_denied():
    p = perm_for_role("invest_agency", "M99")
    assert p["can_view"] is False
