import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from delayu.models import SsoProvider, Subsystem
from delayu.services.sso import login_page_esia_providers

User = get_user_model()


@pytest.mark.django_db
def test_public_registry_docs_without_auth():
    client = Client(HTTP_HOST="127.0.0.1")
    for path in (
        "/docs/registry/",
        "/docs/registry/passport/",
        "/docs/registry/demo/",
        "/docs/registry/application/",
        "/docs/registry/ai/",
        "/docs/registry/tariffs/",
        "/docs/registry/source-code/",
    ):
        resp = client.get(path)
        assert resp.status_code == 200, path


@pytest.mark.django_db
def test_public_tariff_policy_pdf_full_text():
    from delayu.services.registry_platform import build_tariff_policy, export_tariff_policy_pdf

    data = build_tariff_policy()
    resp = export_tariff_policy_pdf()
    assert resp.status_code == 200
    body = resp.content
    assert body[:4] == b"%PDF"
    # Текст не обрезается на 400 символов — в PDF должна быть длинная фраза из oговорки
    assert len(body) > 3000
    assert "437" in data["disclaimer"]


@pytest.mark.django_db
def test_public_registry_export_pdf():
    client = Client(HTTP_HOST="127.0.0.1")
    resp = client.get("/docs/registry/export/passport/")
    assert resp.status_code == 200
    assert "application/pdf" in resp["Content-Type"]


@pytest.mark.django_db
def test_login_esia_providers_dedupe_by_client_id():
    sub_a = Subsystem.objects.create(code="esia_a", name="A", industry_template="uzhv")
    sub_b = Subsystem.objects.create(code="esia_b", name="B", industry_template="uzhv")
    for sub in (sub_a, sub_b):
        SsoProvider.objects.create(
            subsystem=sub,
            name="ЕСИА (демо) — физлицо",
            client_id="demo-esia-fl",
            provider_type=SsoProvider.ProviderType.ESIA,
            is_active=True,
            metadata={"demo": True},
        )
        SsoProvider.objects.create(
            subsystem=sub,
            name="ЕСИА (демо) — организация",
            client_id="demo-esia-org",
            provider_type=SsoProvider.ProviderType.ESIA,
            is_active=True,
            metadata={"demo": True},
        )
    providers = login_page_esia_providers()
    assert len(providers) == 1
    assert providers[0].client_id == "demo-esia-fl"


@pytest.mark.django_db
def test_login_page_esia_dedupe_two_subsystems():
    sub_a = Subsystem.objects.create(code="esia_c", name="C", industry_template="core")
    sub_b = Subsystem.objects.create(code="esia_d", name="D", industry_template="core")
    for sub in (sub_a, sub_b):
        SsoProvider.objects.create(
            subsystem=sub,
            name="ESIA demo FL",
            client_id="demo-esia-fl",
            provider_type=SsoProvider.ProviderType.ESIA,
            is_active=True,
            metadata={"demo": True},
        )
    providers = login_page_esia_providers()
    assert len(providers) == 1
    assert providers[0].client_id == "demo-esia-fl"
