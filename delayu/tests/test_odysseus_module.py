"""Tests for Odysseus platform module (M87) — P0+."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from delayu.data.modules_full import MODULES_FULL
from delayu.models import (
    ModuleCatalog,
    Organization,
    Role,
    RoleModulePermission,
    Subsystem,
    SubsystemMembership,
    SubsystemModule,
)
from delayu.models_odysseus import OdysseusSettings
from delayu.services.odysseus_proxy import path_allowed
from delayu.services.odysseus_settings import check_odysseus_health, ensure_odysseus_settings

User = get_user_model()


@pytest.mark.django_db
def test_m87_in_catalog_data():
    codes = [m["code"] for m in MODULES_FULL]
    assert "M87" in codes


@pytest.mark.django_db
def test_ensure_odysseus_settings_defaults():
    sub = Subsystem.objects.create(
        code="ody-t", name="Ody", industry_template="invest", status="active"
    )
    cfg = ensure_odysseus_settings(sub)
    assert cfg.base_url.startswith("http://127.0.0.1:7000")
    assert cfg.enabled is False
    assert cfg.pinned_ref == ""
    assert OdysseusSettings.objects.filter(subsystem=sub).count() == 1
    again = ensure_odysseus_settings(sub)
    assert again.pk == cfg.pk


@pytest.mark.django_db
def test_check_odysseus_health_ok():
    sub = Subsystem.objects.create(
        code="ody-h", name="Ody H", industry_template="invest", status="active"
    )
    cfg = ensure_odysseus_settings(sub)
    mock_resp = MagicMock(status_code=200)
    with patch("httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.get.return_value = mock_resp
        assert check_odysseus_health(cfg) is True
    cfg.refresh_from_db()
    assert cfg.last_health_ok is True
    assert cfg.last_health_at is not None


@pytest.mark.django_db
def test_check_odysseus_health_down():
    sub = Subsystem.objects.create(
        code="ody-d", name="Ody D", industry_template="invest", status="active"
    )
    cfg = ensure_odysseus_settings(sub)
    with patch("httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.get.side_effect = ConnectionError("down")
        assert check_odysseus_health(cfg) is False
    cfg.refresh_from_db()
    assert cfg.last_health_ok is False


@pytest.fixture
def ody_ctx(db):
    sub = Subsystem.objects.create(
        code="ody-ui", name="Ody UI", industry_template="invest", status="active"
    )
    module = ModuleCatalog.objects.create(code="M87", name="Odysseus workspace")
    SubsystemModule.objects.create(subsystem=sub, module=module, enabled=True)
    org = Organization.objects.create(subsystem=sub, code="o1", name="Org")
    role = Role.objects.create(subsystem=sub, code="invest_admin", name="Admin")
    RoleModulePermission.objects.create(
        role=role,
        module=module,
        can_view=True,
        can_create=True,
        can_change=True,
        can_delete=False,
    )
    user = User.objects.create_user("ody_admin", password="x", is_superuser=True)
    SubsystemMembership.objects.create(
        user=user, subsystem=sub, organization=org, role=role, is_default=True
    )
    cfg = ensure_odysseus_settings(sub)
    return {"sub": sub, "user": user, "cfg": cfg, "module": module}


@pytest.mark.django_db
def test_shell_get_ok(client, ody_ctx):
    client.force_login(ody_ctx["user"])
    resp = client.get(reverse("platform-odysseus"))
    assert resp.status_code == 200
    assert b"Odysseus" in resp.content


@pytest.mark.django_db
def test_settings_post_enables(client, ody_ctx):
    client.force_login(ody_ctx["user"])
    resp = client.post(
        reverse("platform-odysseus-settings"),
        {
            "enabled": "on",
            "base_url": "http://127.0.0.1:7000",
            "embed_mode": "proxy_shell",
            "pinned_ref": "abc123",
            "upstream_url": "https://github.com/odysseus-dev/odysseus.git",
            "vendor_path": "vendor/odysseus",
            "auth_mode": "none_dev",
            "shared_secret": "",
            "timeout_s": "30",
        },
    )
    assert resp.status_code == 302
    ody_ctx["cfg"].refresh_from_db()
    assert ody_ctx["cfg"].enabled is True
    assert ody_ctx["cfg"].pinned_ref == "abc123"


@pytest.mark.django_db
def test_path_allowed_and_denied():
    sub = Subsystem.objects.create(
        code="ody-p", name="Ody P", industry_template="invest", status="active"
    )
    cfg = ensure_odysseus_settings(sub)
    cfg.allowed_path_prefixes = ["/api/", "/assets/"]
    cfg.save()
    assert path_allowed(cfg, "api/v1") is True
    assert path_allowed(cfg, "assets/app.js") is True
    assert path_allowed(cfg, "admin/secret") is False


@pytest.mark.django_db
def test_proxy_disabled_forbidden(client, ody_ctx):
    ody_ctx["cfg"].enabled = False
    ody_ctx["cfg"].save()
    client.force_login(ody_ctx["user"])
    resp = client.get(reverse("platform-odysseus-proxy-root"))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_proxy_allowlist_404(client, ody_ctx):
    cfg = ody_ctx["cfg"]
    cfg.enabled = True
    cfg.allowed_path_prefixes = ["/api/"]
    cfg.save()
    client.force_login(ody_ctx["user"])
    resp = client.get(reverse("platform-odysseus-proxy", kwargs={"path": "secret"}))
    assert resp.status_code == 404


@pytest.mark.django_db
def test_proxy_forwards(client, ody_ctx):
    cfg = ody_ctx["cfg"]
    cfg.enabled = True
    cfg.allowed_path_prefixes = ["/"]
    cfg.save()
    client.force_login(ody_ctx["user"])
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"ok-ody"
    mock_resp.headers = {"content-type": "text/plain"}
    with patch("httpx.Client") as client_cls:
        http = client_cls.return_value.__enter__.return_value
        http.request.return_value = mock_resp
        resp = client.get(reverse("platform-odysseus-proxy-root"))
    assert resp.status_code == 200
    assert resp.content == b"ok-ody"


@pytest.mark.django_db
def test_update_check_missing_vendor(ody_ctx, settings, tmp_path):
    from delayu.services.odysseus_update import check_update

    settings.BASE_DIR = tmp_path
    cfg = ody_ctx["cfg"]
    cfg.vendor_path = "vendor/odysseus"
    cfg.save()
    result = check_update(ody_ctx["sub"])
    assert result.vendor_exists is False
