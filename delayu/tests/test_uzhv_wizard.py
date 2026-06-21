"""Мастера создания УЖВ."""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from delayu.forms_uzhv_wizard import UzhvChainWizardForm
from delayu.models import Organization, Role, Subsystem, SubsystemMembership
from delayu.models_uzhv import HousingAppeal, HousingCitizen, HousingQueueCase

User = get_user_model()


@pytest.fixture
def uzhv_wizard_ctx(db):
    from delayu.models import ModuleCatalog, RoleModulePermission, SubsystemModule

    sub = Subsystem.objects.create(code="uzhv_w", name="УЖВ W", industry_template="uzhv")
    org = Organization.objects.create(subsystem=sub, name="O", code="o")
    role = Role.objects.create(subsystem=sub, code="uzhv_admin", name="Admin")
    user = User.objects.create_user("wizard_user", password="pass")
    for code in ("M22", "M24", "M07"):
        mod, _ = ModuleCatalog.objects.get_or_create(
            code=code, defaults={"name": code, "group": "ops"}
        )
        SubsystemModule.objects.get_or_create(subsystem=sub, module=mod, defaults={"enabled": True})
        RoleModulePermission.objects.get_or_create(
            role=role,
            module=mod,
            defaults={"can_view": True, "can_create": True, "can_change": True},
        )
    SubsystemMembership.objects.create(
        user=user, subsystem=sub, organization=org, role=role, is_default=True
    )
    return sub, user, Client()


@pytest.mark.django_db
def test_chain_form_requires_name_for_new_citizen(uzhv_wizard_ctx):
    sub, _, _ = uzhv_wizard_ctx
    form = UzhvChainWizardForm(
        {"citizen_mode": "new", "create_case": False, "create_appeal": False},
        subsystem=sub,
    )
    assert not form.is_valid()
    assert "last_name" in form.errors


@pytest.mark.django_db
def test_create_hub_and_chain_post(uzhv_wizard_ctx):
    sub, user, client = uzhv_wizard_ctx
    client.force_login(user)
    session = client.session
    session["active_subsystem_id"] = sub.pk
    session.save()

    hub = client.get(reverse("uzhv-create-hub"))
    assert hub.status_code == 200

    resp = client.post(
        reverse("uzhv-create-chain"),
        {
            "citizen_mode": "new",
            "last_name": "Иванов",
            "first_name": "Иван",
            "create_case": "on",
            "case_category": HousingQueueCase.Category.GENERAL,
            "case_status": HousingQueueCase.Status.REGISTERED,
            "create_appeal": "on",
            "appeal_subject": "Вопрос по жилью",
            "received_at": "2026-05-27",
        },
    )
    assert resp.status_code == 302
    assert HousingCitizen.objects.filter(subsystem=sub, last_name="Иванов").exists()
    assert HousingQueueCase.objects.filter(subsystem=sub).exists()
    assert HousingAppeal.objects.filter(subsystem=sub).exists()
