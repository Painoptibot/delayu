import pytest

from delayu.forms_roles import RoleEditForm
from delayu.models import Role, Subsystem
from delayu.services.uzhv_roles import perm_for_role


def test_uzhv_admin_can_create_citizens_m22():
    p = perm_for_role("uzhv_admin", "M22")
    assert p["can_view"] is True
    assert p["can_create"] is True
    assert p["can_change"] is True


def test_uzhv_admin_denied_integrations():
    p = perm_for_role("uzhv_admin", "M42")
    assert p["can_view"] is False


@pytest.mark.django_db
def test_role_edit_form_init_without_attribute_error():
    sub = Subsystem.objects.create(code="uzhv_t", name="T", industry_template="uzhv")
    role = Role.objects.create(subsystem=sub, code="custom", name="Custom")
    form = RoleEditForm(instance=role, subsystem=sub)
    assert "code" in form.fields
