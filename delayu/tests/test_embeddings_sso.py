import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from delayu.models import (
    CaseFile,
    Organization,
    SearchIndexEntry,
    SsoProvider,
    Subsystem,
)
from delayu.services.audit import list_audit_snapshots, save_audit_snapshot
from delayu.services.embeddings import cosine_similarity, embed_text
from delayu.services.pgvector_search import pgvector_available
from delayu.services.retention import purge_expired_cases
from delayu.services.search_index import rebuild_search_index, search_index
from delayu.services.sso import build_authorize_url, resolve_sso_user

User = get_user_model()


@pytest.fixture
def platform_sub(db):
    from delayu.models import ModuleCatalog, Role, RoleModulePermission, SubsystemMembership, SubsystemModule

    sub = Subsystem.objects.create(code="plat360", name="360 test", industry_template="core")
    org = Organization.objects.create(subsystem=sub, code="o1", name="Org")
    role = Role.objects.create(subsystem=sub, code="admin", name="Admin")
    for code, name in [("M01", "Админ"), ("M06", "Архив"), ("M22", "Дела")]:
        mod, _ = ModuleCatalog.objects.get_or_create(code=code, defaults={"name": name, "group": "core"})
        RoleModulePermission.objects.create(role=role, module=mod, can_view=True, can_change=True, can_delete=True)
        SubsystemModule.objects.create(subsystem=sub, module=mod, enabled=True)
    user = User.objects.create_user("plat_user", password="x")
    SubsystemMembership.objects.create(
        user=user, subsystem=sub, organization=org, role=role, is_default=True
    )
    return sub, user, org


@pytest.mark.django_db
def test_embed_text_similarity():
    a = embed_text("жалоба гражданина жилищное")
    b = embed_text("жалоба на жилищные условия")
    c = embed_text("договор поставки оборудования")
    assert cosine_similarity(a, b) > cosine_similarity(a, c)


@pytest.mark.django_db
def test_search_index_with_embeddings(db):
    sub = Subsystem.objects.create(code="emb", name="Emb", industry_template="core")
    org = Organization.objects.create(subsystem=sub, code="o1", name="Org")
    user = User.objects.create_user("emb_user", password="x")
    CaseFile.objects.create(
        subsystem=sub,
        organization=org,
        number="EMB-001",
        title="уникальный токен xyz в описании",
        description="жалоба гражданина",
        created_by=user,
    )
    stats = rebuild_search_index(sub)
    assert stats["case"] == 1
    assert SearchIndexEntry.objects.filter(subsystem=sub).exclude(embedding=[]).exists()
    hits = search_index(sub, "уникальный токен xyz")
    assert hits
    assert hits[0]["type"] == "case"


@pytest.mark.django_db
def test_pgvector_available_sqlite():
    assert pgvector_available() is False


@pytest.mark.django_db
def test_sso_demo_flow(client, db):
    sub = Subsystem.objects.create(code="sso", name="SSO", industry_template="core")
    User.objects.create_user("admin", password="admin")
    provider = SsoProvider.objects.create(
        subsystem=sub,
        name="OIDC Demo",
        provider_type=SsoProvider.ProviderType.OIDC,
        client_id="demo",
        is_active=True,
        metadata={"demo": True, "demo_username": "admin"},
    )
    session = client.session
    session.save()
    request = type("R", (), {"session": session, "build_absolute_uri": lambda self, p: f"http://test{p}"})()
    url = build_authorize_url(provider, request)
    assert "code=demo" in url
    user, meta = resolve_sso_user(provider, "demo", redirect_uri="http://test/callback")
    assert user.username == "admin"
    assert meta["mode"] == "demo"


@pytest.mark.django_db
def test_sso_oidc_production_mock(db):
    sub = Subsystem.objects.create(code="oidc", name="OIDC", industry_template="core")
    User.objects.create_user("oidc_user", password="x")
    provider = SsoProvider.objects.create(
        subsystem=sub,
        name="OIDC Prod",
        provider_type=SsoProvider.ProviderType.OIDC,
        client_id="client",
        is_active=True,
        metadata={
            "token_endpoint": "https://idp.example/token",
            "userinfo_endpoint": "https://idp.example/userinfo",
            "client_secret": "secret",
            "username_claim": "preferred_username",
        },
    )
    token_payload = json.dumps({"access_token": "tok123"}).encode()
    user_payload = json.dumps({"preferred_username": "oidc_user", "sub": "abc"}).encode()

    def fake_urlopen(req, timeout=15):
        url = req.full_url
        body = token_payload if "token" in url else user_payload

        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                return body

        return Resp()

    with patch("delayu.services.sso.request.urlopen", fake_urlopen):
        user, meta = resolve_sso_user(
            provider, "authcode", redirect_uri="http://app/callback"
        )
    assert user.username == "oidc_user"
    assert meta["mode"] == "oidc"


@pytest.mark.django_db
def test_audit_snapshot(platform_sub, settings, tmp_path):
    sub, user, _org = platform_sub
    settings.MEDIA_ROOT = tmp_path
    from delayu.services import audit

    audit.log_action(user, sub, "test.snapshot", "CaseFile", 1)
    result = save_audit_snapshot(sub, mask_pii=True)
    assert (tmp_path / "audit_exports" / result["filename"]).exists()
    listed = list_audit_snapshots(subsystem_code=sub.code)
    assert listed and listed[0]["filename"] == result["filename"]


@pytest.mark.django_db
def test_purge_expired_cases(platform_sub):
    sub, user, org = platform_sub
    yesterday = timezone.now().date() - timezone.timedelta(days=1)
    CaseFile.objects.create(
        subsystem=sub,
        organization=org,
        number="EXP-1",
        title="Expired",
        created_by=user,
        is_archived=True,
        legal_hold=False,
        retention_until=yesterday,
    )
    dry = purge_expired_cases(sub, dry_run=True)
    assert dry["count"] == 1
    live = purge_expired_cases(sub, dry_run=False)
    assert live["deleted"] >= 1
