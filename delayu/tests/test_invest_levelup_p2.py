from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from pypdf import PdfReader

from delayu.models import ModuleCatalog, Organization, Role, RoleModulePermission, Subsystem, SubsystemMembership, SubsystemModule
from delayu.models_invest import (
    InvestOivApproval,
    InvestProject,
    InvestProjectSite,
    InvestProtocol,
    InvestSite,
    InvestStopFactor,
    InvestSupportTrackItem,
)
from delayu.services.invest_bitrix import push_project_to_bitrix
from delayu.services.invest_handoff import InvestHandoffError, request_handoff
from delayu.services.invest_roles import perm_for_role

User = get_user_model()


@pytest.fixture
def levelup_ctx(db):
    subsystem = Subsystem.objects.create(
        code="inv-levelup",
        name="Invest Levelup",
        industry_template="invest",
        status=Subsystem.Status.ACTIVE,
    )
    module = ModuleCatalog.objects.create(code="M22", name="Invest projects")
    SubsystemModule.objects.create(subsystem=subsystem, module=module, enabled=True)
    org = Organization.objects.create(subsystem=subsystem, code="mo-lvl", name="Levelup MO")
    role = Role.objects.create(subsystem=subsystem, code="invest_admin", name="Invest admin")
    RoleModulePermission.objects.create(role=role, module=module, **perm_for_role(role.code, "M22"))
    user = User.objects.create_user("levelup_admin", password="x")
    SubsystemMembership.objects.create(
        user=user,
        subsystem=subsystem,
        organization=org,
        role=role,
        is_default=True,
    )
    site = InvestSite.objects.create(
        subsystem=subsystem,
        organization=org,
        cadastral_number="23:00:0000000:6",
        name="Industrial site",
        address="Krasnodar, Test street",
        area_ha="12.5000",
        status=InvestSite.Status.ACTUAL,
    )
    project = InvestProject.objects.create(
        subsystem=subsystem,
        organization=org,
        code="LVL-6",
        name="Levelup project",
        investor_name="Acme Investor",
        industry="Manufacturing",
        stage="package_ready",
        owner=user,
        investment_amount="150.25",
        jobs_count=42,
        support_measures="Tax benefit",
    )
    InvestProjectSite.objects.create(project=project, site=site, role=InvestProjectSite.Role.SELECTED)
    return {"subsystem": subsystem, "org": org, "user": user, "project": project, "site": site}


@pytest.mark.django_db
def test_project_passport_pdf_contains_core_project_summary(client, levelup_ctx):
    client.force_login(levelup_ctx["user"])

    response = client.get(reverse("invest-project-passport", args=[levelup_ctx["project"].pk]))

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(response.content)).pages)
    assert "LVL-6" in text
    assert "Levelup project" in text
    assert "Acme Investor" in text
    assert "package_ready" in text
    assert "Levelup MO" in text
    assert "150.25" in text
    assert "42" in text
    assert "23:00:0000000:6" in text


@pytest.mark.django_db
def test_project_detail_lists_support_protocols_and_oiv_matrix(client, levelup_ctx):
    project = levelup_ctx["project"]
    InvestSupportTrackItem.objects.create(project=project, title="Subsidy package", status="open")
    InvestProtocol.objects.create(project=project, title="Intent protocol")
    InvestOivApproval.objects.create(project=project, agency_name="Ministry of Economy", status="pending")
    client.force_login(levelup_ctx["user"])

    response = client.get(reverse("invest-project-detail", args=[project.pk]))

    assert response.status_code == 200
    html = response.content.decode()
    assert "Subsidy package" in html
    assert "Intent protocol" in html
    assert "Ministry of Economy" in html


@pytest.mark.django_db
def test_support_track_add_form_creates_item_from_project_detail(client, levelup_ctx):
    client.force_login(levelup_ctx["user"])

    response = client.post(
        reverse("invest-project-support-add", args=[levelup_ctx["project"].pk]),
        {"title": "Infrastructure reimbursement", "status": "in_progress", "due_at": "2026-08-01"},
        follow=True,
    )

    assert response.status_code == 200
    item = InvestSupportTrackItem.objects.get(project=levelup_ctx["project"], title="Infrastructure reimbursement")
    assert item.status == "in_progress"
    assert str(item.due_at) == "2026-08-01"
    assert "Infrastructure reimbursement" in response.content.decode()


@pytest.mark.django_db
def test_protocol_can_link_nullable_document_and_appears_on_project(client, levelup_ctx):
    document = levelup_ctx["subsystem"].documents.create(
        title="Signed intent",
        uploaded_by=levelup_ctx["user"],
        file=SimpleUploadedFile("intent.pdf", b"pdf", content_type="application/pdf"),
    )

    protocol = InvestProtocol.objects.create(
        project=levelup_ctx["project"],
        title="Signed protocol",
        signed_at="2026-07-25",
        document=document,
    )

    assert protocol.document == document


@pytest.mark.django_db
def test_open_stop_factor_blocks_handoff_button_and_bitrix_push(client, levelup_ctx):
    project = levelup_ctx["project"]
    InvestStopFactor.objects.create(project=project, title="No grid capacity", status=InvestStopFactor.Status.BLOCKING)
    client.force_login(levelup_ctx["user"])

    response = client.get(reverse("invest-project-detail", args=[project.pk]))

    assert response.status_code == 200
    html = response.content.decode()
    assert "No grid capacity" in html
    assert "Передача заблокирована" in html
    assert 'disabled' in html

    with pytest.raises(InvestHandoffError, match="стоп-факторы"):
        request_handoff(project=project, user=levelup_ctx["user"], comment="")

    result = push_project_to_bitrix(project=project)
    assert result["pushed"] is False
    assert "stop_factor" in result["blockers"]
