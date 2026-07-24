import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from delayu.models import Organization, Role, Subsystem, SubsystemMembership


@pytest.mark.django_db
def test_subsystem_accepts_invest_template():
    field = Subsystem._meta.get_field("industry_template")
    choice_values = [value for value, _label in field.choices]
    assert "invest" in choice_values

    sub = Subsystem.objects.create(
        code="invest-t", name="Invest T", industry_template="invest", status="active"
    )
    assert sub.industry_template == "invest"
    sub.full_clean()


@pytest.mark.django_db
def test_switch_to_invest_redirects_to_hub(client):
    user = get_user_model().objects.create_user("invest_switch", password="x")
    sub = Subsystem.objects.create(
        code="invest-switch", name="Invest Switch", industry_template="invest", status="active"
    )
    org = Organization.objects.create(subsystem=sub, code="main", name="Main")
    role = Role.objects.create(subsystem=sub, code="invest_user", name="Invest user")
    membership = SubsystemMembership.objects.create(
        user=user, subsystem=sub, organization=org, role=role
    )
    client.force_login(user)

    response = client.post(reverse("platform-switch-subsystem"), {"membership_id": membership.pk})

    assert response.status_code == 302
    assert response["Location"] == reverse("invest-hub")
