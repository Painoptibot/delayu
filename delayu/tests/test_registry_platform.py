import pytest
from django.contrib.auth import get_user_model

from delayu.models import (
    ModuleCatalog,
    Organization,
    Role,
    RoleModulePermission,
    Subsystem,
    SubsystemMembership,
    SubsystemModule,
)
from delayu.services.registry_platform import (
    build_product_passport,
    export_compliance_csv,
    export_passport_pdf,
    seed_registry_catalog,
)

User = get_user_model()


@pytest.fixture
def registry_sub(db):
    sub = Subsystem.objects.create(code="registry_test", name="Реестр тест", industry_template="core")
    org = Organization.objects.create(subsystem=sub, code="o1", name="Org")
    role = Role.objects.create(subsystem=sub, code="admin", name="Admin")
    mod78, _ = ModuleCatalog.objects.get_or_create(code="M78", defaults={"name": "Эксплуатация", "group": "ops"})
    mod22, _ = ModuleCatalog.objects.get_or_create(code="M22", defaults={"name": "Дела", "group": "cases"})
    RoleModulePermission.objects.create(role=role, module=mod78, can_view=True)
    SubsystemModule.objects.create(subsystem=sub, module=mod78, enabled=True)
    SubsystemModule.objects.create(subsystem=sub, module=mod22, enabled=True)
    user = User.objects.create_user("registry_user", password="x")
    SubsystemMembership.objects.create(
        user=user, subsystem=sub, organization=org, role=role, is_default=True
    )
    return sub


@pytest.mark.django_db
def test_seed_registry_catalog():
    ModuleCatalog.objects.get_or_create(
        code="M78", defaults={"name": "Эксплуатация", "group": "ops"}
    )
    seed_registry_catalog()
    result = seed_registry_catalog()
    assert result["release"]
    assert result["compliance"] >= 1


@pytest.mark.django_db
def test_build_product_passport(registry_sub):
    seed_registry_catalog()
    data = build_product_passport(registry_sub)
    assert data["product_name"] == "ДелаЮ"
    assert data["modules_count"] >= 2
    assert len(data["ai_scenarios"]) >= 3
    assert len(data["glossary"]) >= 1


@pytest.mark.django_db
def test_export_passport_pdf(registry_sub):
    seed_registry_catalog()
    resp = export_passport_pdf(registry_sub)
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF" or resp.content[:5] == b"<!DOC"


@pytest.mark.django_db
def test_export_compliance_csv(registry_sub):
    seed_registry_catalog()
    resp = export_compliance_csv(registry_sub)
    body = resp.content.decode("utf-8-sig")
    assert "M78" in body or "M22" in body
    assert "Модуль" in body
