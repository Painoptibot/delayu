from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from delayu.models import (
    ModuleCatalog,
    Organization,
    Role,
    RoleModulePermission,
    Subsystem,
    SubsystemMembership,
    SubsystemModule,
)
from delayu.models_invest import InvestProject, InvestProjectSite, InvestSite, InvestSmevRequest
from delayu.services.invest_roles import perm_for_role

User = get_user_model()


@pytest.fixture
def p6_ctx(db):
    sub = Subsystem.objects.create(
        code="inv-p6",
        name="Invest P6",
        industry_template="invest",
        status=Subsystem.Status.ACTIVE,
    )
    module = ModuleCatalog.objects.create(code="M22", name="Инвестпроекты")
    SubsystemModule.objects.create(subsystem=sub, module=module, enabled=True)
    org = Organization.objects.create(subsystem=sub, code="mo1", name="МО-1")
    role = Role.objects.create(subsystem=sub, code="invest_admin", name="Администратор")
    RoleModulePermission.objects.create(role=role, module=module, **perm_for_role(role.code, "M22"))
    user = User.objects.create_user("p6_admin", password="x")
    SubsystemMembership.objects.create(
        user=user,
        subsystem=sub,
        organization=org,
        role=role,
        is_default=True,
    )
    project = InvestProject.objects.create(
        subsystem=sub,
        organization=org,
        code="P6-1",
        name="Проект P6",
        funnel=InvestProject.Funnel.ATTRACTION,
        stage="site_pick",
    )
    site = InvestSite.objects.create(
        subsystem=sub,
        organization=org,
        cadastral_number="23:01:0000000:101",
        name="Площадка с координатами",
        area_ha="12.5000",
        vri="производство",
        status=InvestSite.Status.ACTUAL,
        latitude="45.123456",
        longitude="38.654321",
        restriction_zones=["Охранная зона ЛЭП", "ЗОУИТ"],
    )
    return {"sub": sub, "org": org, "role": role, "user": user, "project": project, "site": site}


@pytest.mark.django_db
def test_sites_map_page_lists_sites_with_coordinates(client, p6_ctx):
    client.force_login(p6_ctx["user"])

    response = client.get(reverse("invest-sites-map"))

    assert response.status_code == 200
    html = response.content.decode()
    assert "Площадка с координатами" in html
    assert "45.123456" in html
    assert "38.654321" in html


@pytest.mark.django_db
def test_site_compare_shows_up_to_three_candidates(client, p6_ctx):
    sites = [
        p6_ctx["site"],
        InvestSite.objects.create(
            subsystem=p6_ctx["sub"],
            organization=p6_ctx["org"],
            cadastral_number="23:01:0000000:102",
            name="Вторая площадка",
            area_ha="8.0000",
            vri="склад",
            status=InvestSite.Status.IN_REVIEW,
        ),
        InvestSite.objects.create(
            subsystem=p6_ctx["sub"],
            organization=p6_ctx["org"],
            cadastral_number="23:01:0000000:103",
            name="Третья площадка",
            area_ha="4.5000",
            vri="логистика",
            status=InvestSite.Status.DRAFT,
        ),
        InvestSite.objects.create(
            subsystem=p6_ctx["sub"],
            organization=p6_ctx["org"],
            cadastral_number="23:01:0000000:104",
            name="Четвёртая площадка",
            area_ha="6.0000",
            vri="офисы",
        ),
    ]
    client.force_login(p6_ctx["user"])

    response = client.get(reverse("invest-sites-compare"), {"ids": ",".join(str(site.pk) for site in sites)})

    assert response.status_code == 200
    html = response.content.decode()
    assert "23:01:0000000:101" in html
    assert "23:01:0000000:103" in html
    assert "23:01:0000000:104" not in html
    assert "производство" in html


@pytest.mark.django_db
def test_expire_overdue_booking_releases_booked_site(client, p6_ctx):
    link = InvestProjectSite.objects.create(
        project=p6_ctx["project"],
        site=p6_ctx["site"],
        role=InvestProjectSite.Role.BOOKED,
        booked_until=timezone.now() - timedelta(days=1),
    )
    client.force_login(p6_ctx["user"])

    response = client.post(reverse("invest-bookings"), {"action": "expire"}, follow=True)

    assert response.status_code == 200
    link.refresh_from_db()
    assert link.role == InvestProjectSite.Role.CANDIDATE
    assert link.booked_until is None
    assert not InvestProjectSite.objects.filter(role=InvestProjectSite.Role.BOOKED, booked_until__lt=timezone.now()).exists()


@pytest.mark.django_db
def test_site_detail_shows_restriction_zones_and_egrn_history(client, p6_ctx):
    InvestSmevRequest.objects.create(
        subsystem=p6_ctx["sub"],
        site=p6_ctx["site"],
        service=InvestSmevRequest.Service.EGRN,
        status=InvestSmevRequest.Status.APPLIED,
        request_payload={"cadastral_number": p6_ctx["site"].cadastral_number},
        response_payload={"source": "mock-smev-egrn", "area_ha": "12.5", "vri": "производство"},
        finished_at=timezone.now(),
    )
    client.force_login(p6_ctx["user"])

    response = client.get(reverse("invest-site-detail", args=[p6_ctx["site"].pk]))

    assert response.status_code == 200
    html = response.content.decode()
    assert "Охранная зона ЛЭП" in html
    assert "История ЕГРН" in html
    assert "mock-smev-egrn" in html
    assert "Применено к карточке" in html
