from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from delayu.models import Organization, Role, Subsystem, SubsystemMembership
from delayu.models_invest import InvestHandoff, InvestPackageItem, InvestProject, InvestRoadmapItem, InvestSite
from delayu.services.invest_booking import InvestBookingError, book_site
from delayu.services.invest_dashboard import build_dashboard
from delayu.services.invest_handoff import accept_handoff, request_handoff
from delayu.services.invest_package import ensure_package
from delayu.services.invest_scope import projects_for_membership

User = get_user_model()


@pytest.fixture
def invest_e2e_ctx(db):
    sub = Subsystem.objects.create(code="inv-e2e", name="Invest E2E", industry_template="invest", status="active")
    org_a = Organization.objects.create(subsystem=sub, code="mo-a", name="МО А")
    org_b = Organization.objects.create(subsystem=sub, code="mo-b", name="МО Б")
    agency_role = Role.objects.create(subsystem=sub, code="invest_agency", name="Агентство")
    dept_role = Role.objects.create(subsystem=sub, code="invest_dept", name="Департамент")
    mo_role = Role.objects.create(subsystem=sub, code="invest_mo", name="МО")
    agency_user = User.objects.create_user("e2e_agency", password="x")
    dept_user = User.objects.create_user("e2e_dept", password="x")
    mo_user = User.objects.create_user("e2e_mo", password="x")
    mo_membership = SubsystemMembership.objects.create(
        user=mo_user, subsystem=sub, organization=org_a, role=mo_role, is_default=True
    )
    SubsystemMembership.objects.create(
        user=agency_user, subsystem=sub, organization=org_a, role=agency_role, is_default=True
    )
    SubsystemMembership.objects.create(
        user=dept_user, subsystem=sub, organization=org_a, role=dept_role, is_default=True
    )
    project = InvestProject.objects.create(
        subsystem=sub,
        organization=org_a,
        code="P-E2E",
        name="Проект E2E",
        funnel=InvestProject.Funnel.ATTRACTION,
        stage="site_pick",
    )
    other_project = InvestProject.objects.create(
        subsystem=sub,
        organization=org_b,
        code="P-OTHER",
        name="Чужой проект",
        funnel=InvestProject.Funnel.ATTRACTION,
        stage="site_pick",
    )
    site = InvestSite.objects.create(
        subsystem=sub,
        organization=org_a,
        cadastral_number="23:00:0000000:15",
        name="Площадка E2E",
        status=InvestSite.Status.ACTUAL,
    )
    return {
        "sub": sub,
        "org_a": org_a,
        "agency_user": agency_user,
        "dept_user": dept_user,
        "mo_membership": mo_membership,
        "project": project,
        "other_project": other_project,
        "site": site,
    }


def complete_required_package(project):
    package = ensure_package(project)
    package.items.filter(required=True).update(status=InvestPackageItem.Status.ATTACHED)
    return package


@pytest.mark.django_db
def test_agency_books_site_completes_package_and_dept_accepts_handoff(invest_e2e_ctx):
    project = invest_e2e_ctx["project"]

    book_site(project=project, site=invest_e2e_ctx["site"], user=invest_e2e_ctx["agency_user"])
    complete_required_package(project)
    project.stage = "package_ready"
    project.save(update_fields=["stage"])
    handoff = request_handoff(project=project, user=invest_e2e_ctx["agency_user"], comment="Пакет готов")
    accepted_project = accept_handoff(handoff=handoff, user=invest_e2e_ctx["dept_user"])

    accepted_project.refresh_from_db()
    handoff.refresh_from_db()
    dashboard = build_dashboard(invest_e2e_ctx["sub"])
    assert handoff.status == InvestHandoff.Status.ACCEPTED
    assert accepted_project.funnel == InvestProject.Funnel.SUPPORT
    assert accepted_project.stage == "accepted"
    assert accepted_project.roadmap_items.count() == 4
    assert set(accepted_project.roadmap_items.values_list("code", flat=True)) == {
        "land",
        "permits",
        "build",
        "commission",
    }
    assert dashboard["support_counts"] == {"accepted": 1}


@pytest.mark.django_db
def test_mo_user_cannot_see_other_mo_project_via_membership_scope(invest_e2e_ctx):
    qs = projects_for_membership(invest_e2e_ctx["mo_membership"])

    assert set(qs) == {invest_e2e_ctx["project"]}
    assert invest_e2e_ctx["other_project"] not in qs


@pytest.mark.django_db
def test_second_book_on_same_site_fails(invest_e2e_ctx):
    project = invest_e2e_ctx["project"]
    second_project = InvestProject.objects.create(
        subsystem=invest_e2e_ctx["sub"],
        organization=invest_e2e_ctx["org_a"],
        code="P-SECOND",
        name="Второй проект",
        funnel=InvestProject.Funnel.ATTRACTION,
        stage="site_pick",
    )

    book_site(project=project, site=invest_e2e_ctx["site"], user=invest_e2e_ctx["agency_user"])

    with pytest.raises(InvestBookingError, match="Площадка занята проектом P-E2E"):
        book_site(project=second_project, site=invest_e2e_ctx["site"], user=invest_e2e_ctx["agency_user"])


@pytest.mark.django_db
def test_dashboard_reports_overdue_after_past_due_roadmap_item(invest_e2e_ctx):
    InvestRoadmapItem.objects.create(
        project=invest_e2e_ctx["project"],
        code="land",
        title="Земля",
        due_at=timezone.now() - timedelta(days=1),
        status=InvestRoadmapItem.Status.OPEN,
    )

    dashboard = build_dashboard(invest_e2e_ctx["sub"])

    assert dashboard["overdue_count"] == 1
    assert dashboard["bottlenecks_by_org"] == [
        {
            "organization_id": invest_e2e_ctx["org_a"].id,
            "organization_name": invest_e2e_ctx["org_a"].name,
            "overdue_count": 1,
        }
    ]
