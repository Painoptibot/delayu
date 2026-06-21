"""Входящие webhook: ЕПГУ, Telegram."""
import json

import pytest
from django.test import Client

from delayu.models import IntegrationEndpoint, IntegrationMessage, Subsystem
from delayu.models_uzhv import HousingAppeal
from delayu.services.integration_inbound import process_inbound, verify_inbound_access


@pytest.fixture
def uzhv_sub(db):
    return Subsystem.objects.create(code="uzhv_in", name="УЖВ in", industry_template="uzhv")


@pytest.fixture
def epgu_endpoint(uzhv_sub, db):
    from django.contrib.auth import get_user_model
    from delayu.models import Organization, Role, SubsystemMembership

    User = get_user_model()
    org = Organization.objects.create(subsystem=uzhv_sub, name="Org")
    role = Role.objects.create(subsystem=uzhv_sub, code="uzhv_admin", name="Admin")
    user = User.objects.create_user("epgu_actor", password="x")
    SubsystemMembership.objects.create(
        user=user, subsystem=uzhv_sub, organization=org, role=role, is_default=True
    )
    return IntegrationEndpoint.objects.create(
        subsystem=uzhv_sub,
        code="epgu_uzhv",
        name="EPGU",
        endpoint_type=IntegrationEndpoint.EndpointType.GATEWAY,
        is_active=True,
        config={
            "allow_inbound": True,
            "inbound_handler": "uzhv.epgu.appeal",
            "inbound_secret": "test-secret",
        },
    )


@pytest.mark.django_db
def test_verify_inbound_secret(epgu_endpoint):
    class Req:
        headers = {"X-Integration-Secret": "test-secret"}

    assert verify_inbound_access(Req(), epgu_endpoint) is None


@pytest.mark.django_db
def test_epgu_handler_creates_appeal(epgu_endpoint, uzhv_sub):
    result = process_inbound(
        epgu_endpoint,
        {
            "subject": "Жилищный вопрос",
            "body": "Текст",
            "external_id": "EPGU-99",
            "citizen": {"last_name": "Петров", "first_name": "Пётр", "snils": "123-456-789 00"},
        },
    )
    assert result.get("appeal_number")
    assert HousingAppeal.objects.filter(subsystem=uzhv_sub).count() == 1
    assert IntegrationMessage.objects.filter(endpoint=epgu_endpoint, direction="in").exists()


@pytest.mark.django_db
def test_api_integration_inbound_http(epgu_endpoint, uzhv_sub):
    client = Client()
    payload = {
        "subject": "Через API",
        "citizen": {"last_name": "Сидоров", "first_name": "Сидор"},
    }
    resp = client.post(
        f"/api/v1/integration/inbound/{uzhv_sub.code}/epgu_uzhv/",
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_X_INTEGRATION_SECRET="test-secret",
        HTTP_HOST="localhost",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("appeal_id")


@pytest.fixture
def mfc_endpoint(uzhv_sub, db):
    from django.contrib.auth import get_user_model
    from delayu.models import Organization, Role, SubsystemMembership

    User = get_user_model()
    org = Organization.objects.create(subsystem=uzhv_sub, name="Org2")
    role = Role.objects.create(subsystem=uzhv_sub, code="uzhv_admin2", name="Admin2")
    user = User.objects.create_user("mfc_actor", password="x")
    SubsystemMembership.objects.create(
        user=user, subsystem=uzhv_sub, organization=org, role=role, is_default=True
    )
    return IntegrationEndpoint.objects.create(
        subsystem=uzhv_sub,
        code="mfc_uzhv",
        name="MFC",
        endpoint_type=IntegrationEndpoint.EndpointType.GATEWAY,
        is_active=True,
        config={
            "allow_inbound": True,
            "inbound_handler": "uzhv.mfc.application",
            "inbound_secret": "mfc-secret",
        },
    )


@pytest.mark.django_db
def test_mfc_handler_creates_appeal(mfc_endpoint, uzhv_sub):
    result = process_inbound(
        mfc_endpoint,
        {
            "subject": "Заявление МФЦ",
            "body": "Документы приложены",
            "external_id": "MFC-1",
            "citizen": {"last_name": "Иванов", "first_name": "Иван"},
        },
    )
    assert result.get("appeal_number")
    appeal = HousingAppeal.objects.get(subsystem=uzhv_sub)
    assert "МФЦ" in (appeal.body or "")
