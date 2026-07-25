from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from delayu.models import (
    ActivityEvent,
    AuditLog,
    DocumentFile,
    ModuleCatalog,
    Organization,
    Role,
    RoleModulePermission,
    Subsystem,
    SubsystemMembership,
    SubsystemModule,
)
from delayu.models_invest import (
    InvestExternalTask,
    InvestHandoff,
    InvestPackageItem,
    InvestProject,
    InvestRoadmapItem,
)
from delayu.services.invest_flags import ensure_automation_config
from delayu.services.invest_handoff import request_handoff
from delayu.services.invest_package import ensure_package
from delayu.services.invest_roles import perm_for_role

User = get_user_model()


@pytest.fixture
def p4_ctx(db):
    sub = Subsystem.objects.create(
        code="inv-p4", name="Invest P4", industry_template="invest", status="active"
    )
    module = ModuleCatalog.objects.create(code="M22", name="Инвестпроекты")
    SubsystemModule.objects.create(subsystem=sub, module=module, enabled=True)
    org = Organization.objects.create(subsystem=sub, code="mo1", name="МО-1")
    roles = {}
    for code, name in [
        ("invest_admin", "Администратор"),
        ("invest_dept", "Департамент"),
        ("invest_agency", "Агентство"),
    ]:
        role = Role.objects.create(subsystem=sub, code=code, name=name)
        RoleModulePermission.objects.create(role=role, module=module, **perm_for_role(code, "M22"))
        roles[code] = role
    users = {}
    for role_code in roles:
        user = User.objects.create_user(role_code, password="x")
        SubsystemMembership.objects.create(
            user=user,
            subsystem=sub,
            organization=org,
            role=roles[role_code],
            is_default=True,
        )
        users[role_code] = user
    project = InvestProject.objects.create(
        subsystem=sub,
        organization=org,
        code="P4-1",
        name="Проект P4",
        funnel=InvestProject.Funnel.ATTRACTION,
        stage="lead",
    )
    ensure_automation_config(sub)
    return {"sub": sub, "org": org, "users": users, "project": project}


@pytest.mark.django_db
def test_inbox_lists_today_items_and_refreshes_sla(client, p4_ctx):
    project = p4_ctx["project"]
    due_at = timezone.now() - timedelta(days=2)
    InvestRoadmapItem.objects.create(
        project=project,
        code="land",
        title="Просроченная дорожная карта",
        due_at=due_at,
        status=InvestRoadmapItem.Status.OPEN,
    )
    request_handoff(project=project, user=p4_ctx["users"]["invest_agency"], comment="Готово")
    InvestExternalTask.objects.create(
        subsystem=p4_ctx["sub"],
        project=project,
        organization=p4_ctx["org"],
        kind=InvestExternalTask.Kind.MO,
        title="Ответ МО",
        due_at=due_at,
        status=InvestExternalTask.Status.OPEN,
    )
    client.force_login(p4_ctx["users"]["invest_dept"])

    response = client.get(reverse("invest-inbox"))

    assert response.status_code == 200
    html = response.content.decode()
    assert "Просроченная дорожная карта" in html
    assert "Готово" in html
    assert "Ответ МО" in html

    response = client.post(reverse("invest-inbox"), {"action": "refresh_sla"}, follow=True)

    assert response.status_code == 200
    assert AuditLog.objects.filter(subsystem=p4_ctx["sub"], action="invest.sla.refresh").exists()
    assert ActivityEvent.objects.filter(subsystem=p4_ctx["sub"], verb="invest.sla.refresh").exists()


@pytest.mark.django_db
def test_handoff_return_accepts_canned_reason_template(client, p4_ctx):
    project = p4_ctx["project"]
    handoff = request_handoff(project=project, user=p4_ctx["users"]["invest_agency"], comment="Пакет")
    client.force_login(p4_ctx["users"]["invest_dept"])

    response = client.post(
        reverse("invest-handoff-return", args=[handoff.pk]),
        {"comment_template": "missing_required_documents"},
        follow=True,
    )

    assert response.status_code == 200
    handoff.refresh_from_db()
    assert handoff.status == InvestHandoff.Status.RETURNED
    assert handoff.comment == "Верните, пожалуйста: в пакете не хватает обязательных документов."


@pytest.mark.django_db
def test_bulk_stage_updates_same_funnel_projects_and_audits_each_change(client, p4_ctx):
    project = p4_ctx["project"]
    second = InvestProject.objects.create(
        subsystem=p4_ctx["sub"],
        organization=p4_ctx["org"],
        code="P4-2",
        name="Второй",
        funnel=InvestProject.Funnel.ATTRACTION,
        stage="lead",
    )
    client.force_login(p4_ctx["users"]["invest_admin"])

    response = client.post(
        reverse("invest-project-bulk-stage"),
        {"project_ids": [project.pk, second.pk], "stage": "qualify"},
        follow=True,
    )

    assert response.status_code == 200
    assert list(
        InvestProject.objects.filter(pk__in=[project.pk, second.pk]).order_by("code").values_list("stage", flat=True)
    ) == ["qualify", "qualify"]
    assert AuditLog.objects.filter(subsystem=p4_ctx["sub"], action="invest.project.bulk_stage").count() == 2


@pytest.mark.django_db
def test_package_item_can_link_existing_document_file(client, p4_ctx):
    project = p4_ctx["project"]
    package = ensure_package(project)
    item = package.items.get(code="egrn")
    document = DocumentFile.objects.create(
        subsystem=p4_ctx["sub"],
        title="Выписка ЕГРН",
        uploaded_by=p4_ctx["users"]["invest_admin"],
        file=SimpleUploadedFile("egrn.pdf", b"pdf", content_type="application/pdf"),
    )
    client.force_login(p4_ctx["users"]["invest_admin"])

    response = client.post(
        reverse("invest-package-item-update", args=[project.pk, item.pk]),
        {"status": InvestPackageItem.Status.ATTACHED, "document": document.pk},
        follow=True,
    )

    assert response.status_code == 200
    item.refresh_from_db()
    assert item.status == InvestPackageItem.Status.ATTACHED
    assert item.document_id == document.pk
