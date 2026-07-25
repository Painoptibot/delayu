import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from delayu.models import ModuleCatalog, Organization, Role, RoleModulePermission, Subsystem, SubsystemMembership, SubsystemModule
from delayu.models_invest import InvestProject, InvestProjectSite, InvestSite, InvestSmevRequest
from delayu.services.invest_roles import perm_for_role
from delayu.services.invest_smev import apply_smev_response

User = get_user_model()


@pytest.fixture
def p3_ctx(db):
    subsystem = Subsystem.objects.create(
        code="inv-p3",
        name="Invest P3",
        industry_template="invest",
        status=Subsystem.Status.ACTIVE,
    )
    module = ModuleCatalog.objects.create(code="M22", name="Invest projects")
    SubsystemModule.objects.create(subsystem=subsystem, module=module, enabled=True)
    org = Organization.objects.create(subsystem=subsystem, code="mo-p3", name="P3 MO")
    role = Role.objects.create(subsystem=subsystem, code="invest_admin", name="Invest admin")
    RoleModulePermission.objects.create(role=role, module=module, **perm_for_role(role.code, "M22"))
    user = User.objects.create_user("p3_admin", password="x", is_superuser=True)
    SubsystemMembership.objects.create(
        user=user,
        subsystem=subsystem,
        organization=org,
        role=role,
        is_default=True,
    )
    project = InvestProject.objects.create(
        subsystem=subsystem,
        organization=org,
        code="P3-1",
        name="P3 project",
        investor_name="ООО Ромашка",
        industry="АПК",
        stage="site_pick",
        external_ids={"investor_inn": "  7707 083893 "},
    )
    site = InvestSite.objects.create(
        subsystem=subsystem,
        organization=org,
        cadastral_number="23:03:0000000:11",
        name="P3 site",
        completeness_pct=40,
        status=InvestSite.Status.ACTUAL,
    )
    return {"subsystem": subsystem, "org": org, "role": role, "user": user, "project": project, "site": site}


@pytest.mark.django_db
def test_project_inn_check_normalizes_validates_and_renders_button(client, p3_ctx):
    client.force_login(p3_ctx["user"])

    page = client.get(reverse("invest-project-detail", args=[p3_ctx["project"].pk]))
    assert page.status_code == 200
    assert "Проверить ИНН" in page.content.decode()

    response = client.post(reverse("invest-project-inn-check", args=[p3_ctx["project"].pk]), follow=True)

    assert response.status_code == 200
    p3_ctx["project"].refresh_from_db()
    assert p3_ctx["project"].external_ids["investor_inn"] == "7707083893"
    assert p3_ctx["project"].external_ids["investor_inn_valid"] is True
    assert "ИНН проверен" in response.content.decode()


@pytest.mark.django_db
def test_project_form_uses_okved_datalist_without_blocking_free_text(client, p3_ctx):
    client.force_login(p3_ctx["user"])

    page = client.get(reverse("invest-project-edit", args=[p3_ctx["project"].pk]))
    assert page.status_code == 200
    html = page.content.decode()
    assert 'list="invest-okved-industries"' in html
    assert "Обрабатывающие производства" in html

    response = client.post(
        reverse("invest-project-edit", args=[p3_ctx["project"].pk]),
        {
            "organization": p3_ctx["org"].pk,
            "code": p3_ctx["project"].code,
            "name": p3_ctx["project"].name,
            "investor_name": p3_ctx["project"].investor_name,
            "industry": "Свободная отрасль инвестора",
            "description": "",
            "stage": p3_ctx["project"].stage,
            "owner": "",
            "contact_person": "",
            "contact_phone": "",
            "contact_email": "",
            "investment_amount": "",
            "jobs_count": "",
            "support_measures": "",
            "planned_start": "",
            "planned_end": "",
            "municipality_notes": "",
        },
    )

    assert response.status_code == 302
    p3_ctx["project"].refresh_from_db()
    assert p3_ctx["project"].industry == "Свободная отрасль инвестора"


@pytest.mark.django_db
def test_booking_gate_blocks_incomplete_site_until_admin_override(client, p3_ctx):
    client.force_login(p3_ctx["user"])
    url = reverse("invest-site-book", args=[p3_ctx["project"].pk, p3_ctx["site"].pk])

    blocked = client.post(url, follow=True)

    assert blocked.status_code == 200
    assert not InvestProjectSite.objects.filter(project=p3_ctx["project"], site=p3_ctx["site"]).exists()
    assert "полнота карточки" in blocked.content.decode()

    allowed = client.post(url, {"booking_override": "1"}, follow=True)

    assert allowed.status_code == 200
    assert InvestProjectSite.objects.filter(
        project=p3_ctx["project"],
        site=p3_ctx["site"],
        role=InvestProjectSite.Role.BOOKED,
    ).exists()


@pytest.mark.django_db
def test_mo_refresh_campaign_marks_org_sites_and_lists_progress(client, p3_ctx):
    second = InvestSite.objects.create(
        subsystem=p3_ctx["subsystem"],
        organization=p3_ctx["org"],
        cadastral_number="23:03:0000000:12",
        name="Second P3 site",
        completeness_pct=80,
    )
    client.force_login(p3_ctx["user"])

    response = client.post(reverse("invest-sites-campaign"), {"organization": p3_ctx["org"].pk}, follow=True)

    assert response.status_code == 200
    for site in (p3_ctx["site"], second):
        site.refresh_from_db()
        assert site.external_ids["mo_refresh"]["status"] == "queued"
        assert site.external_ids["mo_refresh"]["campaign_id"]
    html = response.content.decode()
    assert "Кампании актуализации МО" in html
    assert "queued" in html
    assert "2" in html


@pytest.mark.django_db
def test_apply_smev_response_stores_field_diff_and_site_detail_shows_it(client, p3_ctx):
    p3_ctx["site"].address = "Старый адрес"
    p3_ctx["site"].save(update_fields=["address", "updated_at"])
    req = InvestSmevRequest.objects.create(
        subsystem=p3_ctx["subsystem"],
        site=p3_ctx["site"],
        service=InvestSmevRequest.Service.EGRN,
        status=InvestSmevRequest.Status.DONE,
        response_payload={
            "source": "mock-smev-egrn",
            "address": "Новый адрес",
            "area_ha": "15.25",
            "land_category": "земли промышленности",
        },
        created_by=p3_ctx["user"],
    )

    apply_smev_response(request=req, user=p3_ctx["user"])

    req.refresh_from_db()
    assert req.response_payload["field_diff"]["address"] == {"old": "Старый адрес", "new": "Новый адрес"}
    client.force_login(p3_ctx["user"])
    response = client.get(reverse("invest-site-detail", args=[p3_ctx["site"].pk]))
    assert response.status_code == 200
    html = response.content.decode()
    assert "Изменения СМЭВ" in html
    assert "Новый адрес" in html
