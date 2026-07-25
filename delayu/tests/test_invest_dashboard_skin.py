from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.conf import settings
from django.urls import reverse

from delayu.models import ModuleCatalog, Organization, Role, RoleModulePermission, Subsystem, SubsystemMembership, SubsystemModule
from delayu.services.invest_roles import perm_for_role

User = get_user_model()

SKIN_CSS_NAME = "invest-dashboard-skin.css"
SKIN_PAGES = (
    "invest-cockpit",
    "invest-dashboard",
    "invest-kanban",
    "invest-inbox",
)
REQUIRED_MARKERS = (
    "invest-dash",
    "invest-dash__hero",
    "invest-dash__kpi",
    "invest-dash__panel",
)
BANNED_CSS_SNIPPETS = (
    "linear-gradient(135deg, #667eea",
    "purple-to-indigo",
    "#7c3aed",
    "openstreetmap.org",
    "leaflet",
)


@pytest.fixture
def skin_ctx(db):
    subsystem = Subsystem.objects.create(
        code="inv-skin",
        name="Invest Skin",
        industry_template="invest",
        status=Subsystem.Status.ACTIVE,
    )
    module = ModuleCatalog.objects.create(code="M22", name="Invest projects")
    SubsystemModule.objects.create(subsystem=subsystem, module=module, enabled=True)
    org = Organization.objects.create(subsystem=subsystem, code="mo-skin", name="Skin MO")
    role = Role.objects.create(subsystem=subsystem, code="invest_admin", name="Invest admin")
    RoleModulePermission.objects.create(role=role, module=module, **perm_for_role(role.code, "M22"))
    user = User.objects.create_user("skin_admin", password="x", is_superuser=True)
    SubsystemMembership.objects.create(
        user=user,
        subsystem=subsystem,
        organization=org,
        role=role,
        is_default=True,
    )
    return {"user": user, "subsystem": subsystem}


def _css_path() -> Path:
    return Path(settings.BASE_DIR) / "src" / "assets" / "css" / SKIN_CSS_NAME


@pytest.mark.django_db
@pytest.mark.parametrize("url_name", SKIN_PAGES)
def test_invest_dashboard_pages_load_skin_css_and_markers(client, skin_ctx, url_name):
    client.force_login(skin_ctx["user"])
    response = client.get(reverse(url_name))
    assert response.status_code == 200
    html = response.content.decode()
    assert SKIN_CSS_NAME in html
    for marker in REQUIRED_MARKERS:
        assert marker in html, f"missing marker {marker} on {url_name}"


@pytest.mark.django_db
def test_invest_dashboard_skin_css_tokens_and_audit_bans():
    css_path = _css_path()
    assert css_path.is_file(), f"missing skin stylesheet at {css_path}"
    css = css_path.read_text(encoding="utf-8")
    assert "--invest-dash-accent" in css
    assert "--invest-dash-surface" in css
    assert "@keyframes invest-dash-rise" in css
    assert ".invest-dash__kpi" in css
    assert "@media (max-width:" in css
    lowered = css.lower()
    for banned in BANNED_CSS_SNIPPETS:
        assert banned.lower() not in lowered, f"banned design token found: {banned}"
