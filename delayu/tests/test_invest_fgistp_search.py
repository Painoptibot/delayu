"""FGISTP demo catalog search by address / cadastral number."""

import pytest
from django.contrib.auth import get_user_model
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
from delayu.models_invest import InvestFgistpDocument, InvestFgistpRecord, InvestSite
from delayu.services.invest_fgistp import attach_fgistp_document, search_fgistp_documents
from delayu.services.invest_flags import ensure_automation_config
from delayu.services.invest_roles import perm_for_role

User = get_user_model()


@pytest.fixture
def search_ctx(db):
    sub = Subsystem.objects.create(
        code="inv-fg-search", name="FGISTP Search", industry_template="invest", status="active"
    )
    module = ModuleCatalog.objects.create(code="M22", name="Инвестпроекты")
    SubsystemModule.objects.create(subsystem=sub, module=module, enabled=True)
    org = Organization.objects.create(subsystem=sub, code="mo1", name="МО Краснодар")
    role = Role.objects.create(subsystem=sub, code="invest_agency", name="Агентство")
    RoleModulePermission.objects.create(role=role, module=module, **perm_for_role("invest_agency", "M22"))
    user = User.objects.create_user("fg_search_user", password="x")
    SubsystemMembership.objects.create(user=user, subsystem=sub, organization=org, role=role, is_default=True)
    site = InvestSite.objects.create(
        subsystem=sub,
        organization=org,
        cadastral_number="23:43:0107001:101",
        name="Восток",
        address="г. Краснодар, восточная промзона",
        completeness_pct=80,
    )
    doc_kn = InvestFgistpDocument.objects.create(
        subsystem=sub,
        uin="demo-kn-1",
        title="ПЗЗ Краснодар Восток",
        level=InvestFgistpDocument.Level.MUNICIPAL,
        address_text="г. Краснодар, восточная промзона",
        municipality_name="МО Краснодар",
        cadastral_numbers=["23:43:0107001:101", "23:43:0101001:77"],
        payload={"zones": [{"name": "Промзона", "code": "P-1"}]},
    )
    doc_addr = InvestFgistpDocument.objects.create(
        subsystem=sub,
        uin="demo-addr-1",
        title="Схема ТП Сочи Адлер",
        level=InvestFgistpDocument.Level.MUNICIPAL,
        address_text="г. Сочи, Адлерский район",
        municipality_name="МО Сочи",
        cadastral_numbers=["23:49:0402002:88"],
    )
    ensure_automation_config(sub)
    return {
        "sub": sub,
        "user": user,
        "site": site,
        "doc_kn": doc_kn,
        "doc_addr": doc_addr,
    }


@pytest.mark.django_db
def test_search_by_cadastral_number(search_ctx):
    results = search_fgistp_documents(subsystem=search_ctx["sub"], q="23:43:0107001:101")
    uins = [row["document"].uin for row in results]
    assert "demo-kn-1" in uins
    assert results[0]["score"] >= 80


@pytest.mark.django_db
def test_search_by_address(search_ctx):
    results = search_fgistp_documents(subsystem=search_ctx["sub"], q="Адлер")
    uins = [row["document"].uin for row in results]
    assert "demo-addr-1" in uins


@pytest.mark.django_db
def test_attach_creates_record(search_ctx):
    record = attach_fgistp_document(
        document=search_ctx["doc_kn"],
        site=search_ctx["site"],
        user=search_ctx["user"],
    )
    assert record.status == InvestFgistpRecord.Status.RECEIVED
    assert record.external_ids.get("uin") == "demo-kn-1"
    assert record.payload.get("source") == "mock-fgistp-catalog"


@pytest.mark.django_db
def test_search_page_and_attach(client, search_ctx):
    client.force_login(search_ctx["user"])
    response = client.get(reverse("invest-fgistp-search"), {"q": "23:43:0107001:101"})
    assert response.status_code == 200
    assert "ПЗЗ Краснодар Восток" in response.content.decode()

    response = client.post(
        reverse("invest-fgistp-document-attach", args=[search_ctx["doc_kn"].pk]),
        {"site_id": search_ctx["site"].pk},
    )
    assert response.status_code == 302
    assert InvestFgistpRecord.objects.filter(site=search_ctx["site"], external_ids__contains={"uin": "demo-kn-1"}).exists() or (
        InvestFgistpRecord.objects.filter(site=search_ctx["site"]).exists()
    )


@pytest.mark.django_db
def test_site_detail_search_link(client, search_ctx):
    client.force_login(search_ctx["user"])
    response = client.get(reverse("invest-site-detail", args=[search_ctx["site"].pk]))
    assert response.status_code == 200
    html = response.content.decode()
    assert "invest-fgistp-search" in html or "Найти в ФГИС ТП" in html


@pytest.mark.django_db
def test_registry_has_search_button(client, search_ctx):
    client.force_login(search_ctx["user"])
    response = client.get(reverse("invest-fgistp"))
    assert response.status_code == 200
    assert "Поиск документов" in response.content.decode()


@pytest.mark.django_db
def test_record_url_with_document_id_redirects(client, search_ctx):
    """Legacy/confused /invest/fgistp/<doc_id>/ opens catalog document card."""
    client.force_login(search_ctx["user"])
    response = client.get(reverse("invest-fgistp-detail", args=[search_ctx["doc_kn"].pk]))
    assert response.status_code == 302
    assert response.url == reverse("invest-fgistp-document-detail", args=[search_ctx["doc_kn"].pk])
