"""Тесты webhook и событий УЖВ."""
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from delayu.models import IntegrationEndpoint, IntegrationMessage, Subsystem
from delayu.models_uzhv import HousingAppeal, HousingCitizen, HousingQueueCase
from delayu.services.integration_events import emit_integration_event, endpoint_handles_event
from delayu.services.integrations import _process_http_outbound, process_outbound


@pytest.mark.django_db
def test_endpoint_handles_event_filter():
    ep = IntegrationEndpoint(config={"events": ["uzhv.appeal.status_changed"]})
    assert endpoint_handles_event(ep, "uzhv.appeal.status_changed")
    assert not endpoint_handles_event(ep, "uzhv.case.status_changed")


@pytest.mark.django_db
def test_emit_integration_event_enqueue(uzhv_subsystem):
    ep = IntegrationEndpoint.objects.create(
        subsystem=uzhv_subsystem,
        code="wh_test",
        name="Test WH",
        endpoint_type=IntegrationEndpoint.EndpointType.WEBHOOK,
        is_active=True,
        config={
            "webhook_url": "https://example.com/hook",
            "events": ["uzhv.appeal.status_changed"],
        },
    )
    n = emit_integration_event(
        uzhv_subsystem,
        "uzhv.appeal.status_changed",
        {"id": 1, "appeal_number": "ОБ-1"},
    )
    assert n == 1
    msg = IntegrationMessage.objects.filter(endpoint=ep).first()
    assert msg.payload["event"] == "uzhv.appeal.status_changed"


@pytest.mark.django_db
def test_process_http_outbound_success(uzhv_subsystem):
    ep = IntegrationEndpoint.objects.create(
        subsystem=uzhv_subsystem,
        code="wh_http",
        name="HTTP",
        endpoint_type=IntegrationEndpoint.EndpointType.WEBHOOK,
        config={"webhook_url": "https://example.com/hook"},
        max_retries=3,
    )
    msg = IntegrationMessage.objects.create(
        endpoint=ep,
        direction=IntegrationMessage.Direction.OUT,
        payload={"event": "test"},
        status=IntegrationMessage.Status.PENDING,
    )
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_resp
    mock_cm.__exit__.return_value = None
    with patch("urllib.request.urlopen", return_value=mock_cm):
        out = _process_http_outbound(msg)
    out.refresh_from_db()
    assert out.status == IntegrationMessage.Status.SENT


@pytest.mark.django_db
def test_appeal_status_change_emits_webhook(uzhv_subsystem, uzhv_citizen, uzhv_user):
    IntegrationEndpoint.objects.create(
        subsystem=uzhv_subsystem,
        code="wh_appeal",
        name="WH",
        endpoint_type=IntegrationEndpoint.EndpointType.WEBHOOK,
        is_active=True,
        config={
            "webhook_url": "https://example.com/h",
            "events": ["uzhv.appeal.status_changed"],
        },
    )
    appeal = HousingAppeal.objects.create(
        subsystem=uzhv_subsystem,
        citizen=uzhv_citizen,
        appeal_number="ОБ-TEST-1",
        subject="Test",
        body="Body",
        status=HousingAppeal.Status.REGISTERED,
        assignee=uzhv_user,
        created_by=uzhv_user,
        due_date=timezone.now().date() + timedelta(days=30),
    )
    from delayu.services.uzhv_appeal_status import record_appeal_status_change

    record_appeal_status_change(
        appeal,
        old_status=HousingAppeal.Status.REGISTERED,
        new_status=HousingAppeal.Status.IN_WORK,
        user=uzhv_user,
    )
    assert IntegrationMessage.objects.filter(
        endpoint__code="wh_appeal",
        payload__event="uzhv.appeal.status_changed",
    ).exists()


@pytest.fixture
def uzhv_subsystem(db):
    return Subsystem.objects.create(
        code="uzhv_int",
        name="УЖВ int",
        industry_template="uzhv",
    )


@pytest.fixture
def uzhv_citizen(uzhv_subsystem):
    return HousingCitizen.objects.create(
        subsystem=uzhv_subsystem,
        last_name="Иванов",
        first_name="Иван",
    )


@pytest.fixture
def uzhv_user(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user("int_user", password="x")
