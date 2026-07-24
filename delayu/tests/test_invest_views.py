import pytest
from django import forms
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
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
from delayu.models_invest import InvestHandoff, InvestPackageItem, InvestProject, InvestProjectSite, InvestSite
from delayu.services.invest_handoff import request_handoff
from delayu.services.invest_package import ensure_package
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
    mo_role = Role.objects.create(subsystem=sub, code="invest_mo", name="МО")
    viewer_role = Role.objects.create(subsystem=sub, code="invest_viewer", name="Наблюдатель")
    for role in (agency_role, mo_role, viewer_role):
        RoleModulePermission.objects.create(role=role, module=module, **perm_for_role(role.code, "M22"))
    agency_user = User.objects.create_user("invest_agency", password="x")
    mo_user = User.objects.create_user("invest_mo", password="x")
    viewer_user = User.objects.create_user("invest_viewer", password="x")
    SubsystemMembership.objects.create(
        user=agency_user, subsystem=sub, organization=org, role=agency_role, is_default=True
    )
    SubsystemMembership.objects.create(
        user=mo_user, subsystem=sub, organization=org, role=mo_role, is_default=True
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
        "mo_user": mo_user,
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
        ("invest-handoffs", ()),
        ("invest-package-detail", ("project",)),
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


@pytest.mark.django_db
def test_invest_handoff_request_creates_requested_handoff(client, invest_view_ctx):
    client.force_login(invest_view_ctx["agency_user"])

    response = client.post(
        reverse("invest-handoff-request", args=[invest_view_ctx["project"].pk]),
        {"comment": "Пакет готов"},
        follow=True,
    )

    assert response.status_code == 200
    handoff = InvestHandoff.objects.get(project=invest_view_ctx["project"])
    assert handoff.status == InvestHandoff.Status.REQUESTED
    assert handoff.comment == "Пакет готов"
    assert "Передача запрошена".encode() in response.content


@pytest.mark.django_db
def test_invest_handoff_accept_not_ready_shows_error(client, invest_view_ctx):
    client.force_login(invest_view_ctx["agency_user"])
    handoff = request_handoff(project=invest_view_ctx["project"], user=invest_view_ctx["agency_user"])
    ensure_package(invest_view_ctx["project"])

    response = client.post(reverse("invest-handoff-accept", args=[handoff.pk]), follow=True)

    assert response.status_code == 200
    handoff.refresh_from_db()
    assert handoff.status == InvestHandoff.Status.REQUESTED
    assert "Пакет не готов".encode() in response.content


@pytest.mark.django_db
def test_invest_package_item_status_update_uploads_file(client, invest_view_ctx):
    client.force_login(invest_view_ctx["agency_user"])
    package = ensure_package(invest_view_ctx["project"])
    item = package.items.get(code="egrn")
    upload = SimpleUploadedFile("egrn.pdf", b"pdf", content_type="application/pdf")

    response = client.post(
        reverse("invest-package-item-update", args=[invest_view_ctx["project"].pk, item.pk]),
        {"status": InvestPackageItem.Status.ATTACHED, "file": upload},
        follow=True,
    )

    assert response.status_code == 200
    item.refresh_from_db()
    assert item.status == InvestPackageItem.Status.ATTACHED
    assert item.file.name.startswith("invest/packages/egrn")
    assert item.file.name.endswith(".pdf")
    assert "Пункт пакета обновлён".encode() in response.content


@pytest.mark.django_db
def test_invest_mo_can_upload_apply_and_skip_import_rows(client, invest_view_ctx):
    client.force_login(invest_view_ctx["mo_user"])
    upload = SimpleUploadedFile(
        "mo.csv",
        b"code,name,stage\nP-NEW,Imported,lead\n",
        content_type="text/csv",
    )

    response = client.post(reverse("invest-imports"), {"file": upload}, follow=True)

    assert response.status_code == 200
    batch = invest_view_ctx["sub"].invest_import_batches.get()
    new_project_row = batch.rows.get(action="new_project")
    gap_row = batch.rows.filter(action="gap").first()
    assert gap_row is not None

    response = client.post(reverse("invest-import-row-apply", args=[batch.pk, new_project_row.pk]), follow=True)

    assert response.status_code == 200
    assert InvestProject.objects.filter(code="P-NEW", name="Imported").exists()
    new_project_row.refresh_from_db()
    assert new_project_row.resolution == "applied"

    response = client.post(reverse("invest-import-row-skip", args=[batch.pk, gap_row.pk]), follow=True)

    assert response.status_code == 200
    gap_row.refresh_from_db()
    assert gap_row.resolution == "skipped"


@pytest.mark.django_db
@pytest.mark.parametrize("user_key", ["agency_user", "viewer_user"])
def test_invest_import_denies_agency_and_viewer_roles(client, invest_view_ctx, user_key):
    client.force_login(invest_view_ctx[user_key])
    upload = SimpleUploadedFile(
        "mo.csv",
        b"code,name,stage\nP-DENIED,Denied,lead\n",
        content_type="text/csv",
    )

    response = client.post(reverse("invest-imports"), {"file": upload})

    assert response.status_code == 403
    assert invest_view_ctx["sub"].invest_import_batches.count() == 0
