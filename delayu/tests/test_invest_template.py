import pytest
from delayu.models import Subsystem


@pytest.mark.django_db
def test_subsystem_accepts_invest_template():
    sub = Subsystem.objects.create(
        code="invest-t", name="Invest T", industry_template="invest", status="active"
    )
    assert sub.industry_template == "invest"
