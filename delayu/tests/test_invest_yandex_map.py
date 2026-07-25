from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse

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
def yandex_map_ctx(db):
    subsystem = Subsystem.objects.create(
        code="inv-yandex",
        name="Invest Yandex",
        industry_template="invest",
        status=Subsystem.Status.ACTIVE,
    )
    module = ModuleCatalog.objects.create(code="M22", name="Инвестпроекты")
    SubsystemModule.objects.create(subsystem=subsystem, module=module, enabled=True)
    org = Organization.objects.create(subsystem=subsystem, code="mo1", name="МО-1")
    role = Role.objects.create(subsystem=subsystem, code="invest_admin", name="Администратор")
    RoleModulePermission.objects.create(role=role, module=module, **perm_for_role(role.code, "M22"))
    user = User.objects.create_user("yandex_admin", password="x")
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
        cadastral_number="23:01:0000000:201",
        name="Yandex площадка",
        address="Краснодар, Красная, 1",
        status=InvestSite.Status.ACTUAL,
        latitude="45.123456",
        longitude="38.654321",
        restriction_zones=[
            {"name": "Санитарная зона", "coords": [[45.120000, 38.650000], [45.121000, 38.651000], [45.122000, 38.650000]]},
            {"name": "ЗОУИТ без контура"},
        ],
    )
    project = InvestProject.objects.create(
        subsystem=subsystem,
        organization=org,
        code="YMAP-1",
        name="Проект с бронью",
        funnel=InvestProject.Funnel.ATTRACTION,
        stage="site_pick",
    )
    InvestProjectSite.objects.create(project=project, site=site, role=InvestProjectSite.Role.BOOKED)
    return {"subsystem": subsystem, "org": org, "user": user, "site": site}


@pytest.mark.django_db
@override_settings(YANDEX_MAPS_API_KEY="test-yandex-key")
def test_sites_map_uses_yandex_only(client, yandex_map_ctx):
    client.force_login(yandex_map_ctx["user"])

    response = client.get(reverse("invest-sites-map"))

    assert response.status_code == 200
    html = response.content.decode()
    assert "api-maps.yandex.ru/2.1/?apikey=test-yandex-key" in html
    assert "ymaps.Clusterer" in html
    assert "https://yandex.ru/maps/?pt=38.654321,45.123456&amp;z=15" in html
    assert "Санитарная зона" in html
    assert "Забронирован" in html
    assert "openstreetmap" not in html.lower()
    assert "leaflet" not in html.lower()


@pytest.mark.django_db
@override_settings(YANDEX_MAPS_API_KEY="")
def test_sites_map_without_key_shows_table_without_osm_or_leaflet(client, yandex_map_ctx):
    client.force_login(yandex_map_ctx["user"])

    response = client.get(reverse("invest-sites-map"))

    assert response.status_code == 200
    html = response.content.decode()
    assert "Укажите YANDEX_MAPS_API_KEY" in html
    assert "Yandex площадка" in html
    assert "api-maps.yandex.ru" not in html
    assert "openstreetmap" not in html.lower()
    assert "leaflet" not in html.lower()


@pytest.mark.django_db
@override_settings(YANDEX_MAPS_API_KEY="geo-key")
def test_site_edit_geocode_uses_yandex_service(client, yandex_map_ctx):
    client.force_login(yandex_map_ctx["user"])
    site = yandex_map_ctx["site"]

    with patch("delayu.views_invest.geocode_address", return_value=(Decimal("45.035470"), Decimal("38.975313"))) as mock_geocode:
        response = client.post(
            reverse("invest-site-edit", args=[site.pk]),
            {
                "action": "geocode",
                "organization": yandex_map_ctx["org"].pk,
                "cadastral_number": site.cadastral_number,
                "name": site.name,
                "address": "Краснодар, Красная, 1",
                "area_ha": site.area_ha or "",
                "land_category": site.land_category,
                "vri": site.vri,
                "right_type": site.right_type,
                "encumbrances": site.encumbrances,
                "zone_info": site.zone_info,
                "restriction_zones": "[]",
                "status": site.status,
                "completeness_pct": site.completeness_pct,
                "latitude": site.latitude,
                "longitude": site.longitude,
            },
            follow=True,
        )

    assert response.status_code == 200
    mock_geocode.assert_called_once_with("Краснодар, Красная, 1")
    site.refresh_from_db()
    assert site.latitude == Decimal("45.035470")
    assert site.longitude == Decimal("38.975313")
