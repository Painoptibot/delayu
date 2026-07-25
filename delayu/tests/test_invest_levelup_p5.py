from datetime import datetime, timezone as datetime_timezone

import pytest
from django.apps import apps
from django.contrib.auth import get_user_model
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from delayu.models import ModuleCatalog, Organization, Role, RoleModulePermission, Subsystem, SubsystemMembership, SubsystemModule
from delayu.models_invest import InvestPackage, InvestPackageItem, InvestProject, InvestProjectSite, InvestRoadmapItem, InvestSite
from delayu.services.invest_roles import perm_for_role

User = get_user_model()


@pytest.fixture
def p5_ctx(db):
    subsystem = Subsystem.objects.create(
        code="inv-p5",
        name="Invest P5",
        industry_template="invest",
        status=Subsystem.Status.ACTIVE,
    )
    module = ModuleCatalog.objects.create(code="M22", name="Invest projects")
    SubsystemModule.objects.create(subsystem=subsystem, module=module, enabled=True)
    org = Organization.objects.create(subsystem=subsystem, code="mo-p5", name="P5 MO")
    hot_org = Organization.objects.create(subsystem=subsystem, code="mo-hot", name="Hot MO")
    role = Role.objects.create(subsystem=subsystem, code="invest_admin", name="Invest admin")
    RoleModulePermission.objects.create(role=role, module=module, **perm_for_role(role.code, "M22"))
    user = User.objects.create_user("p5-admin", password="x", is_superuser=True)
    SubsystemMembership.objects.create(
        user=user,
        subsystem=subsystem,
        organization=org,
        role=role,
        is_default=True,
    )
    return {"sub": subsystem, "org": org, "hot_org": hot_org, "role": role, "user": user}


def _project(ctx, *, code, org=None, funnel=InvestProject.Funnel.ATTRACTION, created_at=None):
    project = InvestProject.objects.create(
        subsystem=ctx["sub"],
        organization=org or ctx["org"],
        code=code,
        name=code,
        investor_name="Investor",
        funnel=funnel,
        stage="lead" if funnel == InvestProject.Funnel.ATTRACTION else "accepted",
    )
    if created_at:
        InvestProject.objects.filter(pk=project.pk).update(created_at=created_at)
        project.refresh_from_db()
    return project


def _url(name):
    try:
        return reverse(name)
    except NoReverseMatch as exc:
        pytest.fail(f"{name} route missing: {exc}")


def _quarter_target_model():
    try:
        return apps.get_model("delayu", "InvestQuarterTarget")
    except LookupError as exc:
        pytest.fail(f"InvestQuarterTarget model missing: {exc}")


@pytest.mark.django_db
def test_cockpit_service_reuses_dashboard_with_sla_heat_and_quarter_progress(p5_ctx):
    from delayu.services import invest_dashboard

    build_cockpit = getattr(invest_dashboard, "build_cockpit", None)
    assert build_cockpit is not None, "build_cockpit service missing"

    now = datetime(2026, 7, 15, 12, tzinfo=datetime_timezone.utc)
    target_model = _quarter_target_model()
    target_model.objects.create(
        subsystem=p5_ctx["sub"],
        year=2026,
        quarter=3,
        attraction_goal=4,
    )
    high = _project(p5_ctx, code="P5-HIGH", org=p5_ctx["hot_org"], created_at=now)
    medium = _project(p5_ctx, code="P5-MED", created_at=now)
    _project(p5_ctx, code="P5-SUP", funnel=InvestProject.Funnel.SUPPORT, created_at=now)
    ready_package = InvestPackage.objects.create(project=high)
    InvestPackageItem.objects.create(package=ready_package, code="ready", title="Ready", status=InvestPackageItem.Status.ATTACHED)
    site = InvestSite.objects.create(
        subsystem=p5_ctx["sub"],
        organization=p5_ctx["org"],
        cadastral_number="23:05:0000000:25",
        name="Booked site",
    )
    InvestProjectSite.objects.create(project=high, site=site, role=InvestProjectSite.Role.BOOKED)
    InvestRoadmapItem.objects.create(
        project=high,
        code="late",
        title="Overdue",
        status=InvestRoadmapItem.Status.OPEN,
        due_at=now - timezone.timedelta(days=1),
    )
    InvestRoadmapItem.objects.create(
        project=medium,
        code="soon",
        title="Due soon",
        status=InvestRoadmapItem.Status.OPEN,
        due_at=now + timezone.timedelta(days=2),
    )

    cockpit = build_cockpit(p5_ctx["sub"], now=now)

    assert cockpit["kpis"]["projects_total"] == 3
    assert cockpit["kpis"]["attraction"] == 2
    assert cockpit["kpis"]["support"] == 1
    assert cockpit["kpis"]["overdue"] == 1
    assert cockpit["kpis"]["packages_ready_pct"] == 100
    assert cockpit["kpis"]["active_bookings"] == 1
    assert cockpit["sla_risk"]["high_count"] == 1
    assert cockpit["sla_risk"]["medium_count"] == 1
    assert cockpit["sla_risk"]["projects"][0]["risk"] == "high"
    assert cockpit["heat_by_mo"][0]["organization_name"] == "Hot MO"
    assert cockpit["quarter_target"]["goal"] == 4
    assert cockpit["quarter_target"]["actual"] == 3
    assert cockpit["quarter_target"]["progress_pct"] == 75


@pytest.mark.django_db
def test_cockpit_page_and_meeting_brief_pdf(client, p5_ctx):
    project = _project(p5_ctx, code="P5-PDF")
    InvestRoadmapItem.objects.create(
        project=project,
        code="brief-risk",
        title="Brief risk",
        status=InvestRoadmapItem.Status.OVERDUE,
        due_at=timezone.now() - timezone.timedelta(days=1),
    )
    client.force_login(p5_ctx["user"])

    cockpit = client.get(_url("invest-cockpit"))
    assert cockpit.status_code == 200
    html = cockpit.content.decode()
    assert "Executive cockpit" in html
    assert "SLA risk" in html
    assert "Yandex heat later" in html

    brief = client.get(_url("invest-dashboard-brief"))
    assert brief.status_code == 200
    assert brief["Content-Type"] == "application/pdf"
    assert brief.content.startswith(b"%PDF")
    assert b"Invest meeting brief" in brief.content


@pytest.mark.django_db
def test_project_detail_shows_high_sla_risk(client, p5_ctx):
    project = _project(p5_ctx, code="P5-DETAIL")
    InvestRoadmapItem.objects.create(
        project=project,
        code="detail-risk",
        title="Detail risk",
        status=InvestRoadmapItem.Status.OPEN,
        due_at=timezone.now() - timezone.timedelta(days=1),
    )
    client.force_login(p5_ctx["user"])

    response = client.get(reverse("invest-project-detail", args=[project.pk]))

    assert response.status_code == 200
    assert response.context["sla_risk"]["risk"] == "high"
    assert "Высокий SLA risk" in response.content.decode()
