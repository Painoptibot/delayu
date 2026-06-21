"""Тесты интеграции DaData."""
import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings

from delayu.services import dadata as dadata_service

User = get_user_model()


@pytest.mark.django_db
@override_settings(DADATA_API_KEY="test-token", DADATA_SECRET_KEY="")
def test_suggest_unknown_type():
    result = dadata_service.suggest("unknown", "москва")
    assert result.get("error") == "unknown_type"


@pytest.mark.django_db
@override_settings(DADATA_API_KEY="")
def test_suggest_not_configured():
    result = dadata_service.suggest("address", "краснодар")
    assert result["suggestions"] == []
    assert result.get("configured") is False


@pytest.mark.django_db
@override_settings(DADATA_API_KEY="token")
def test_geocode_from_address():
    fake = {
        "suggestions": [
            {"data": {"geo_lat": "45.03", "geo_lon": "38.97"}},
        ]
    }
    with patch.object(dadata_service, "_post", return_value=fake):
        lat, lng = dadata_service.geocode_from_address("Краснодар, ул. Красная")
    assert lat is not None and lng is not None
    assert float(lat) == pytest.approx(45.03)
    assert float(lng) == pytest.approx(38.97)


@pytest.mark.django_db
@override_settings(DADATA_API_KEY="token")
def test_dadata_suggest_api_requires_login():
    client = Client()
    resp = client.post(
        "/api/v1/dadata/suggest/",
        data=json.dumps({"type": "address", "query": "краснодар"}),
        content_type="application/json",
    )
    assert resp.status_code == 302


@pytest.mark.django_db
@override_settings(DADATA_API_KEY="token")
def test_dadata_suggest_api_authenticated(db):
    from django.test import RequestFactory

    from delayu.views_dadata import dadata_suggest

    fake = {"suggestions": [{"value": "Иванов Иван"}]}
    user = User.objects.create_user("dadata_tester", password="test")
    request = RequestFactory().post(
        "/api/v1/dadata/suggest/",
        data=json.dumps({"type": "fio", "query": "Иванов", "extra": {"parts": ["SURNAME"]}}),
        content_type="application/json",
    )
    request.user = user
    with patch.object(dadata_service, "suggest", return_value=fake) as mock_suggest:
        resp = dadata_suggest(request)
    assert resp.status_code == 200
    data = json.loads(resp.content)
    assert data["suggestions"][0]["value"] == "Иванов Иван"
    mock_suggest.assert_called_once()
    assert mock_suggest.call_args[0][0] == "fio"
