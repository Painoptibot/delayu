"""PY-01 — колонки выгрузки ГИС ЖКХ."""
import pytest

from delayu.models import Subsystem
from delayu.models_uzhv import MunicipalBuilding
from delayu.services.uzhv_fund_import import import_fund_csv

CSV = """address;premise_number;cadastral_number;floors;year_built;uk_name;gis_object_id
ул. GIS, 1;10;23:43:1:1;5;1970;УК Тест;GIS-001
"""


@pytest.mark.django_db
def test_import_fund_csv_gis_columns():
    sub = Subsystem.objects.create(code="gis", name="G", industry_template="uzhv")
    result = import_fund_csv(sub, CSV)
    assert not result.errors
    b = MunicipalBuilding.objects.get(subsystem=sub, address="ул. GIS, 1")
    assert b.cadastral_number == "23:43:1:1"
    assert b.floors == 5
    assert b.year_built == 1970
    assert "УК Тест" in b.notes
    assert "GIS-001" in b.notes
