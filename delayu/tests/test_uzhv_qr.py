"""QR-коды сущностей УЖВ."""
import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from delayu.models import Organization, Role, Subsystem, SubsystemMembership
from delayu.models_uzhv import HousingAppeal, MunicipalBuilding
from delayu.views_qr import uzhv_qr

User = get_user_model()


@pytest.fixture
def uzhv_ctx(db):
    sub = Subsystem.objects.create(code="uzhv_qr", name="УЖВ QR", industry_template="uzhv")
    org = Organization.objects.create(subsystem=sub, name="O", code="o")
    role = Role.objects.create(subsystem=sub, code="admin", name="A")
    user = User.objects.create_user("qr_user", password="x")
    SubsystemMembership.objects.create(
        user=user, subsystem=sub, organization=org, role=role, is_default=True
    )
    return sub, user


@pytest.mark.django_db
def test_uzhv_qr_building_svg(uzhv_ctx):
    sub, user = uzhv_ctx
    b = MunicipalBuilding.objects.create(subsystem=sub, address="ул. Тест, 1")
    rf = RequestFactory()
    req = rf.get(f"/uzhv/qr/buildings/{b.pk}.svg")
    req.user = user
    resp = uzhv_qr(req, "buildings", b.pk)
    assert resp.status_code == 200
    assert b"svg" in resp.content.lower()
