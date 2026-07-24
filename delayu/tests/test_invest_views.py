import pytest
from django import forms
from django.contrib.auth import get_user_model
from django.urls import reverse

from delayu.forms_invest import InvestProjectForm
from delayu.models import (
    ModuleCatalog,
    Organization,
    Role,
    RoleModulePermission,
    Subsystem,
    SubsystemMembership,
    SubsystemModule,
)
from delayu.models_invest import InvestProject, InvestProjectSite, InvestSite
from delayu.services.invest_roles import perm_for_role

User = get_user_model()


@pytest.fixture
def invest_view_ctx(db):
    sub = Subsystem.objects.create(
        code="inv-views", name="Invest Views", industry_template="invest", status="active"
    )
    module = ModuleCatalog.objects.create(code="M22", name="Инвестпроекты")
    SubsystemModule.objects.create(subsystem=sub, module=module, enabled=True)
    org = Organization.objects.create(subsystem=sub, code="mo1", name="МО-1")
    agency_role = Role.objects.create(subsystem=sub, code="invest_agency", name="Агентство")
    viewer_role = Role.objects.create(subsystem=sub, code="invest_viewer", name="Наблюдатель")
    for role in (agency_role, viewer_role):
        RoleModulePermission.objects.create(role=role, module=module, **perm_for_role(role.code, "M22"))
    agency_user = User.objects.create_user("invest_agency", password="x")
    viewer_user = User.objects.create_user("invest_viewer", password="x")
    SubsystemMembership.objects.create(
        user=agency_user, subsystem=sub, organization=org, role=agency_role, is_default=True
    )
    SubsystemMembership.objects.create(
        user=viewer_user, subsystem=sub, organization=org, role=viewer_role, is_default=True
    )
    project = InvestProject.objects.create(
        subsystem=sub,
        organization=org,
        code="P-1",
        name="Проект 1",
        investor_name="Инвестор",
        funnel=InvestProject.Funnel.ATTRACTION,
        stage="lead",
    )
    conflict_project = InvestProject.objects.create(
        subsystem=sub,
        organization=org,
        code="P-2",
        name="Проект 2",
        funnel=InvestProject.Funnel.ATTRACTION,
        stage="site_pick",
    )
    site = InvestSite.objects.create(
        subsystem=sub,
        organization=org,
        cadastral_number="23:00:0000000:1",
        name="Площадка 1",
        status=InvestSite.Status.ACTUAL,
    )
    InvestProjectSite.objects.create(
        project=conflict_project,
        site=site,
        role=InvestProjectSite.Role.BOOKED,
    )
    return {
        "sub": sub,
        "org": org,
        "agency_user": agency_user,
        "viewer_user": viewer_user,
        "project": project,
        "conflict_project": conflict_project,
        "site": site,
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name,args",
    [
        ("invest-hub", ()),
        ("invest-projects", ()),
        ("invest-project-detail", ("project",)),
        ("invest-project-create", ()),
        ("invest-project-edit", ("project",)),
        ("invest-sites", ()),
        ("invest-site-detail", ("site",)),
        ("invest-site-create", ()),
    ],
)
def test_invest_views_get_200(client, invest_view_ctx, url_name, args):
    client.force_login(invest_view_ctx["agency_user"])
    resolved_args = [invest_view_ctx[arg].pk if arg in invest_view_ctx else arg for arg in args]

    response = client.get(reverse(url_name, args=resolved_args))

    assert response.status_code == 200


@pytest.mark.django_db
def test_invest_project_form_excludes_funnel(client, invest_view_ctx):
    client.force_login(invest_view_ctx["agency_user"])

    response = client.get(reverse("invest-project-create"))

    assert response.status_code == 200
    assert b'name="funnel"' not in response.content
    assert "Привлечение".encode() in response.content


@pytest.mark.django_db
def test_invest_project_form_create_stage_choices_start_at_lead(invest_view_ctx):
    membership = SubsystemMembership.objects.get(
        user=invest_view_ctx["agency_user"], subsystem=invest_view_ctx["sub"]
    )

    form = InvestProjectForm(membership=membership)

    assert isinstance(form.fields["stage"], forms.ChoiceField)
    assert isinstance(form.fields["stage"].widget, forms.Select)
    assert [value for value, _label in form.fields["stage"].choices] == ["lead", "qualify"]


@pytest.mark.django_db
def test_invest_viewer_cannot_post_create(client, invest_view_ctx):
    client.force_login(invest_view_ctx["viewer_user"])

    response = client.post(
        reverse("invest-project-create"),
        {
            "organization": invest_view_ctx["org"].pk,
            "code": "P-2",
            "name": "Проект 2",
            "stage": "lead",
        },
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_invest_project_form_rejects_invalid_stage_transition(invest_view_ctx):
    project = invest_view_ctx["project"]
    membership = SubsystemMembership.objects.get(
        user=invest_view_ctx["agency_user"], subsystem=invest_view_ctx["sub"]
    )

    form = InvestProjectForm(
        data={
            "organization": invest_view_ctx["org"].pk,
            "code": project.code,
            "name": project.name,
            "investor_name": project.investor_name,
            "industry": project.industry,
            "stage": "site_pick",
            "owner": "",
            "investment_amount": "",
            "jobs_count": "",
        },
        instance=project,
        membership=membership,
    )

    assert not form.is_valid()
    assert "stage" in form.errors


@pytest.mark.django_db
def test_invest_site_booking_conflict_shows_error_message(client, invest_view_ctx):
    client.force_login(invest_view_ctx["agency_user"])

    response = client.post(
        reverse("invest-site-book", args=[invest_view_ctx["project"].pk, invest_view_ctx["site"].pk]),
        follow=True,
    )

    assert response.status_code == 200
    assert "Площадка занята проектом P-2".encode() in response.content
