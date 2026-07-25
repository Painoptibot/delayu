import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from delayu.menu import build_menu_for_membership
from delayu.models import ModuleCatalog, Organization, Role, RoleModulePermission, Subsystem, SubsystemMembership, SubsystemModule
from delayu.models_invest import InvestProject, InvestProjectSite, InvestSite
from delayu.services.invest_roles import perm_for_role

User = get_user_model()


@pytest.fixture
def p9_ctx(db):
    sub = Subsystem.objects.create(
        code="inv-p9", name="Invest P9", industry_template="invest", status=Subsystem.Status.ACTIVE
    )
    modules = {
        code: ModuleCatalog.objects.create(code=code, name=name)
        for code, name in {
            "M01": "Администрирование",
            "M15": "Дашборды",
            "M22": "Инвестпроекты",
        }.items()
    }
    for module in modules.values():
        SubsystemModule.objects.create(subsystem=sub, module=module, enabled=True)
    org = Organization.objects.create(subsystem=sub, code="mo1", name="МО-1")
    roles = {}
    users = {}
    memberships = {}
    for role_code, role_name in [
        ("invest_agency", "Агентство"),
        ("invest_dept", "Департамент"),
        ("invest_mo", "МО"),
        ("invest_admin", "Администратор"),
    ]:
        role = Role.objects.create(subsystem=sub, code=role_code, name=role_name)
        for module_code, module in modules.items():
            RoleModulePermission.objects.create(role=role, module=module, **perm_for_role(role_code, module_code))
        user = User.objects.create_user(role_code, password="x")
        membership = SubsystemMembership.objects.create(
            user=user,
            subsystem=sub,
            organization=org,
            role=role,
            is_default=True,
        )
        roles[role_code] = role
        users[role_code] = user
        memberships[role_code] = membership
    site = InvestSite.objects.create(
        subsystem=sub,
        organization=org,
        cadastral_number="23:43:0101001:77",
        name="Площадка P9",
        status=InvestSite.Status.ACTUAL,
    )
    return {"sub": sub, "org": org, "users": users, "memberships": memberships, "site": site}


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role_code,expected_title",
    [
        ("invest_agency", "Агентство развития"),
        ("invest_dept", "Департамент инвестиций"),
        ("invest_mo", "Муниципальный кабинет"),
        ("invest_admin", "Администрирование инвестконтура"),
    ],
)
def test_invest_hub_exposes_role_home_for_each_role(client, p9_ctx, role_code, expected_title):
    client.force_login(p9_ctx["users"][role_code])

    response = client.get(reverse("invest-hub"))

    assert response.status_code == 200
    assert response.context["role_home"]["role_code"] == role_code
    assert response.context["role_home"]["title"] == expected_title
    assert response.context["role_home"]["widgets"]
    assert expected_title.encode() in response.content


@pytest.mark.django_db
def test_invest_agency_menu_hides_platform_subsystems(p9_ctx):
    menu = build_menu_for_membership(p9_ctx["memberships"]["invest_agency"])
    urls = [item.get("url") for item in menu if "url" in item]

    assert "platform-subsystems" not in urls


@pytest.mark.django_db
def test_custom_invest_menu_hides_platform_subsystems_for_agency(p9_ctx):
    p9_ctx["sub"].menu_layout = [
        {
            "header": "Администрирование",
            "items": [{"url": "platform-subsystems", "roles": []}],
        }
    ]
    p9_ctx["sub"].save(update_fields=["menu_layout"])

    menu = build_menu_for_membership(p9_ctx["memberships"]["invest_agency"])
    urls = [item.get("url") for item in menu if "url" in item]

    assert "platform-subsystems" not in urls


@pytest.mark.django_db
def test_invest_project_create_auto_assigns_owner_when_blank(client, p9_ctx):
    client.force_login(p9_ctx["users"]["invest_agency"])

    response = client.post(
        reverse("invest-project-create"),
        {
            "organization": p9_ctx["org"].pk,
            "code": "P9-OLD",
            "name": "Old create",
            "stage": "lead",
            "owner": "",
            "investment_amount": "",
            "jobs_count": "",
        },
    )

    assert response.status_code == 302
    project = InvestProject.objects.get(code="P9-OLD")
    assert project.owner == p9_ctx["users"]["invest_agency"]


@pytest.mark.django_db
def test_invest_project_wizard_creates_project_with_site_note_and_owner(client, p9_ctx):
    client.force_login(p9_ctx["users"]["invest_agency"])
    wizard_url = reverse("invest-project-wizard")

    response = client.post(
        wizard_url,
        {
            "step": "1",
            "organization": p9_ctx["org"].pk,
            "code": "P9-WIZ",
            "name": "Wizard project",
            "investor_name": "ООО Визард",
        },
    )
    assert response.status_code == 302
    assert response["Location"] == f"{wizard_url}?step=2"

    response = client.post(wizard_url, {"step": "2", "site": p9_ctx["site"].pk})
    assert response.status_code == 302
    assert response["Location"] == f"{wizard_url}?step=3"

    response = client.post(wizard_url, {"step": "3", "package_note": "Подготовить пакет передачи"})

    project = InvestProject.objects.get(code="P9-WIZ")
    assert response.status_code == 302
    assert response["Location"] == reverse("invest-project-detail", args=[project.pk])
    assert project.owner == p9_ctx["users"]["invest_agency"]
    assert project.municipality_notes == "Подготовить пакет передачи"
    assert InvestProjectSite.objects.filter(project=project, site=p9_ctx["site"]).exists()
