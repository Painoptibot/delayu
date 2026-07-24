import pytest
from delayu.models import Subsystem


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
