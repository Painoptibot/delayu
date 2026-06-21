import pytest
from django.contrib.auth import get_user_model

from delayu.models import IntegrationEndpoint, Organization, Role, Subsystem, SubsystemMembership
from delayu.models_uzhv import HousingQueueCase
from delayu.services.integration_inbound import process_inbound


@pytest.mark.django_db
def test_1c_inbound_creates_case():
    sub = Subsystem.objects.create(code="uzhv_1c", name="T", industry_template="uzhv")
    User = get_user_model()
    org = Organization.objects.create(subsystem=sub, name="O")
    role = Role.objects.create(subsystem=sub, code="uzhv_admin", name="A")
    user = User.objects.create_user("actor1c", password="x")
    SubsystemMembership.objects.create(user=user, subsystem=sub, organization=org, role=role)
    ep = IntegrationEndpoint.objects.create(
        subsystem=sub,
        code="external_1c_uzhv",
        name="1C",
        endpoint_type=IntegrationEndpoint.EndpointType.EXTERNAL_1C,
        is_active=True,
        config={"allow_inbound": True, "inbound_handler": "external.1c.case"},
    )
    result = process_inbound(
        ep,
        {
            "external_id": "1C-100",
            "citizen": {"last_name": "Тестов", "first_name": "Один"},
            "status": "registered",
        },
    )
    assert result.get("action") == "created"
    assert HousingQueueCase.objects.filter(subsystem=sub).count() == 1
