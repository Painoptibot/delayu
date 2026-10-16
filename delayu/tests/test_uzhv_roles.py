import pytest

from delayu.forms_roles import RoleEditForm
from delayu.models import Role, Subsystem
from delayu.services.uzhv_roles import perm_for_role


def test_uzhv_admin_can_create_citizens_m22():
    p = perm_for_role("uzhv_admin", "M22")
    assert p["can_view"] is True
    assert p["can_create"] is True
    assert p["can_change"] is True


def test_support_chat_open_to_every_uzhv_role():
    for code in (
        "uzhv_admin",
        "uzhv_head",
        "uzhv_deputy",
        "uzhv_manager",
        "uzhv_queue_spec",
        "uzhv_orphan_spec",
        "uzhv_contract_spec",
        "uzhv_fund_spec",
        "uzhv_inspector",
        "uzhv_appeals_spec",
        "uzhv_report_spec",
        "uzhv_specialist",
        "uzhv_viewer",
    ):
        perm = perm_for_role(code, "U04")
        assert perm["can_view"] is True, code
        assert perm["can_create"] is True, code


def test_support_reply_is_for_staff_only():
    assert perm_for_role("uzhv_viewer", "U04")["can_change"] is False
    assert perm_for_role("uzhv_head", "U04")["can_change"] is True
    assert perm_for_role("uzhv_admin", "U04")["can_change"] is True


def test_uzhv_admin_denied_integrations():
    p = perm_for_role("uzhv_admin", "M42")
    assert p["can_view"] is False


@pytest.mark.django_db
def test_role_edit_form_init_without_attribute_error():
    sub = Subsystem.objects.create(code="uzhv_t", name="T", industry_template="uzhv")
    role = Role.objects.create(subsystem=sub, code="custom", name="Custom")
    form = RoleEditForm(instance=role, subsystem=sub)
    assert "code" in form.fields
