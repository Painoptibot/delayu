import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from delayu.models import (
    AuditLog,
    ModuleCatalog,
    Organization,
    Role,
    RoleModulePermission,
    Subsystem,
    SubsystemMembership,
    SubsystemModule,
)
from delayu.models_invest import (
    InvestInvestor,
    InvestPackageItem,
    InvestPackageSnapshot,
    InvestProject,
)
from delayu.services.invest_handoff import accept_handoff, request_handoff, return_handoff
from delayu.services.invest_package import ensure_package
from delayu.services.invest_roles import perm_for_role

User = get_user_model()


@pytest.fixture
def invest_p5_ctx(db):
    sub = Subsystem.objects.create(
        code="inv-p5",
        name="Invest P5",
        industry_template="invest",
        status=Subsystem.Status.ACTIVE,
    )
    module = ModuleCatalog.objects.create(code="M22", name="Инвестпроекты")
    SubsystemModule.objects.create(subsystem=sub, module=module, enabled=True)
    org = Organization.objects.create(subsystem=sub, code="mo1", name="МО-1")
    agency_role = Role.objects.create(subsystem=sub, code="invest_agency", name="Агентство")
    dept_role = Role.objects.create(subsystem=sub, code="invest_dept", name="Департамент")
    for role in (agency_role, dept_role):
        RoleModulePermission.objects.create(role=role, module=module, **perm_for_role(role.code, "M22"))
    agency_user = User.objects.create_user("p5_agency", password="x")
    dept_user = User.objects.create_user("p5_dept", password="x")
    SubsystemMembership.objects.create(
        user=agency_user,
        subsystem=sub,
        organization=org,
        role=agency_role,
        is_default=True,
    )
    SubsystemMembership.objects.create(
        user=dept_user,
        subsystem=sub,
        organization=org,
        role=dept_role,
        is_default=True,
    )
    investor = InvestInvestor.objects.create(
        subsystem=sub,
        name="ООО Ромашка",
        inn="2308123456",
        extras={"contact": "director@example.test"},
    )
    project = InvestProject.objects.create(
        subsystem=sub,
        organization=org,
        code="P5-1",
        name="Завод Ромашка",
        investor_name="ООО Ромашка",
        investor_entity=investor,
        funnel=InvestProject.Funnel.ATTRACTION,
        stage="package_ready",
    )
    return {
        "sub": sub,
        "org": org,
        "investor": investor,
        "project": project,
        "agency_user": agency_user,
        "dept_user": dept_user,
    }


@pytest.mark.django_db
def test_investor_list_and_detail_show_linked_projects(client, invest_p5_ctx):
    client.force_login(invest_p5_ctx["agency_user"])

    response = client.get(reverse("invest-investors"))

    assert response.status_code == 200
    assert "ООО Ромашка".encode() in response.content
    assert b"2308123456" in response.content

    response = client.get(reverse("invest-investor-detail", args=[invest_p5_ctx["investor"].pk]))

    assert response.status_code == 200
    assert "Завод Ромашка".encode() in response.content
    assert b"P5-1" in response.content


@pytest.mark.django_db
def test_dedupe_page_lists_duplicate_pairs_and_ignore_persists_state(client, invest_p5_ctx):
    duplicate = InvestProject.objects.create(
        subsystem=invest_p5_ctx["sub"],
        organization=invest_p5_ctx["org"],
        code="P5-2",
        name=invest_p5_ctx["project"].name.upper(),
        investor_name="ООО Ромашка",
        funnel=InvestProject.Funnel.ATTRACTION,
        stage="lead",
    )
    client.force_login(invest_p5_ctx["agency_user"])

    response = client.get(reverse("invest-dedupe"))

    assert response.status_code == 200
    assert b"P5-1" in response.content
    assert b"P5-2" in response.content
    assert "Совпадает наименование".encode() in response.content

    response = client.post(
        reverse("invest-dedupe-ignore"),
        {"left_id": invest_p5_ctx["project"].pk, "right_id": duplicate.pk},
        follow=True,
    )

    assert response.status_code == 200
    invest_p5_ctx["project"].refresh_from_db()
    duplicate.refresh_from_db()
    expected_key = f"{invest_p5_ctx['project'].pk}:{duplicate.pk}"
    assert expected_key in invest_p5_ctx["project"].external_ids["dedupe_ignored"]
    assert expected_key in duplicate.external_ids["dedupe_ignored"]
    assert b"P5-1" not in response.content
    assert b"P5-2" not in response.content


@pytest.mark.django_db
def test_handoff_accept_and_return_create_package_status_snapshots(invest_p5_ctx):
    project = invest_p5_ctx["project"]
    package = ensure_package(project)
    package.items.update(status=InvestPackageItem.Status.ATTACHED)
    item = package.items.get(code="egrn")
    item.status = InvestPackageItem.Status.OVERDUE
    item.save(update_fields=["status"])
    handoff = request_handoff(project=project, user=invest_p5_ctx["agency_user"])

    accept_handoff(handoff=handoff, user=invest_p5_ctx["dept_user"])

    accepted_snapshot = InvestPackageSnapshot.objects.get(project=project, handoff=handoff)
    assert accepted_snapshot.decision == "accepted"
    assert accepted_snapshot.package == package
    assert accepted_snapshot.payload["items"][0]["code"]
    assert any(
        entry["code"] == "egrn" and entry["status"] == InvestPackageItem.Status.OVERDUE
        for entry in accepted_snapshot.payload["items"]
    )

    project.funnel = InvestProject.Funnel.ATTRACTION
    project.stage = "package_ready"
    project.save(update_fields=["funnel", "stage"])
    returned = request_handoff(project=project, user=invest_p5_ctx["agency_user"])
    return_handoff(handoff=returned, user=invest_p5_ctx["dept_user"], comment="Доработать пакет")

    returned_snapshot = InvestPackageSnapshot.objects.get(project=project, handoff=returned)
    assert returned_snapshot.decision == "returned"
    assert returned_snapshot.payload["handoff_comment"] == "Доработать пакет"


@pytest.mark.django_db
def test_package_detail_lists_snapshots(client, invest_p5_ctx):
    package = ensure_package(invest_p5_ctx["project"])
    InvestPackageSnapshot.objects.create(
        project=invest_p5_ctx["project"],
        package=package,
        decision="returned",
        payload={"items": [{"code": "egrn", "title": "Выписка ЕГРН", "status": "missing"}]},
    )
    client.force_login(invest_p5_ctx["agency_user"])

    response = client.get(reverse("invest-package-detail", args=[invest_p5_ctx["project"].pk]))

    assert response.status_code == 200
    assert "Версии пакета".encode() in response.content
    assert "Возвращена".encode() in response.content
    assert b"egrn" in response.content


@pytest.mark.django_db
def test_project_detail_shows_audit_trail_and_completeness_coach(client, invest_p5_ctx):
    AuditLog.objects.create(
        user=invest_p5_ctx["dept_user"],
        subsystem=invest_p5_ctx["sub"],
        action="invest.project.update",
        model_name="InvestProject",
        object_id=str(invest_p5_ctx["project"].pk),
        payload={"field": "stage"},
    )
    client.force_login(invest_p5_ctx["agency_user"])

    response = client.get(reverse("invest-project-detail", args=[invest_p5_ctx["project"].pk]))

    assert response.status_code == 200
    assert "Полнота карточки".encode() in response.content
    assert "Добавьте отрасль".encode() in response.content
    assert "Журнал изменений".encode() in response.content
    assert b"invest.project.update" in response.content
