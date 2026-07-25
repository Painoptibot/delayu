import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from delayu.models import ModuleCatalog, Organization, Role, RoleModulePermission, Subsystem, SubsystemMembership, SubsystemModule, UserProfile
from delayu.models_invest import InvestAutomationConfig, InvestProject, InvestProjectComment, InvestRoadmapItem
from delayu.services.invest_roles import perm_for_role

User = get_user_model()


@pytest.fixture
def p6_ctx(db):
    subsystem = Subsystem.objects.create(
        code="inv-p6", name="Invest P6", industry_template="invest", status=Subsystem.Status.ACTIVE
    )
    module = ModuleCatalog.objects.create(code="M22", name="Invest projects")
    SubsystemModule.objects.create(subsystem=subsystem, module=module, enabled=True)
    org = Organization.objects.create(subsystem=subsystem, code="mo-p6", name="P6 MO")
    roles = {}
    users = {}
    for role_code in ["invest_admin", "invest_dept", "invest_viewer"]:
        role = Role.objects.create(subsystem=subsystem, code=role_code, name=role_code)
        RoleModulePermission.objects.create(role=role, module=module, **perm_for_role(role_code, "M22"))
        user = User.objects.create_user(role_code, password="x")
        SubsystemMembership.objects.create(
            user=user,
            subsystem=subsystem,
            organization=org,
            role=role,
            is_default=True,
        )
        roles[role_code] = role
        users[role_code] = user
    project = InvestProject.objects.create(
        subsystem=subsystem,
        organization=org,
        code="P6-1",
        name="Viewer project",
        investor_name="Limited Investor",
        industry="Manufacturing",
        stage="lead",
        contact_person="Private Person",
        contact_phone="+7 900 000",
        contact_email="private@example.test",
        investment_amount="10.00",
    )
    return {"sub": subsystem, "org": org, "roles": roles, "users": users, "project": project}


@pytest.mark.django_db
def test_investor_viewer_role_gets_limited_project_view(client, p6_ctx):
    client.force_login(p6_ctx["users"]["invest_viewer"])

    response = client.get(reverse("invest-investor-view", args=[p6_ctx["project"].pk]))

    assert response.status_code == 200
    html = response.content.decode()
    assert "Viewer project" in html
    assert "Limited Investor" in html
    assert "lead" in html
    assert reverse("invest-project-edit", args=[p6_ctx["project"].pk]) not in html
    assert "Private Person" not in html
    assert "private@example.test" not in html


@pytest.mark.django_db
def test_invest_inbox_renders_mobile_card_classes(client, p6_ctx):
    InvestRoadmapItem.objects.create(
        project=p6_ctx["project"],
        code="p6-overdue",
        title="Mobile overdue item",
        status=InvestRoadmapItem.Status.OVERDUE,
    )
    client.force_login(p6_ctx["users"]["invest_dept"])

    response = client.get(reverse("invest-inbox"))

    assert response.status_code == 200
    html = response.content.decode()
    assert "invest-inbox-card" in html
    assert "Mobile overdue item" in html


@pytest.mark.django_db
def test_role_home_overrides_save_to_config_and_drive_hub(client, p6_ctx):
    client.force_login(p6_ctx["users"]["invest_admin"])

    response = client.post(
        reverse("invest-role-homes"),
        {
            "role_code": "invest_viewer",
            "title": "Investor Observer",
            "blurb": "Read-only investor-facing workspace.",
        },
        follow=True,
    )

    assert response.status_code == 200
    cfg = InvestAutomationConfig.objects.get(subsystem=p6_ctx["sub"])
    assert cfg.options["role_homes"]["invest_viewer"]["title"] == "Investor Observer"
    assert cfg.options["role_homes"]["invest_viewer"]["blurb"] == "Read-only investor-facing workspace."

    client.force_login(p6_ctx["users"]["invest_viewer"])
    response = client.get(reverse("invest-hub"))
    assert response.status_code == 200
    assert response.context["role_home"]["title"] == "Investor Observer"
    assert "Read-only investor-facing workspace." in response.content.decode()


@pytest.mark.django_db
def test_project_detail_lists_and_accepts_comments(client, p6_ctx):
    client.force_login(p6_ctx["users"]["invest_admin"])

    response = client.post(
        reverse("invest-project-comment-add", args=[p6_ctx["project"].pk]),
        {"body": "Decision note for project"},
        follow=True,
    )

    assert response.status_code == 200
    comment = InvestProjectComment.objects.get(project=p6_ctx["project"])
    assert comment.author == p6_ctx["users"]["invest_admin"]
    assert comment.body == "Decision note for project"
    assert "Decision note for project" in response.content.decode()


@pytest.mark.django_db
def test_invest_onboarding_tracks_ten_step_checklist(client, p6_ctx):
    client.force_login(p6_ctx["users"]["invest_dept"])

    response = client.get(reverse("invest-onboarding"))

    assert response.status_code == 200
    assert len(response.context["invest_onboarding_steps"]) == 10
    first_step = response.context["invest_onboarding_steps"][0]["id"]

    response = client.post(reverse("invest-onboarding"), {"step_id": first_step}, follow=True)

    assert response.status_code == 200
    profile = UserProfile.objects.get(user=p6_ctx["users"]["invest_dept"])
    assert first_step in profile.onboarding_state["invest"]["completed"]
    assert response.context["invest_onboarding_completed"] == 1
