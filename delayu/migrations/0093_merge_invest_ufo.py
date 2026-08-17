# Merge invest extracts/FGISTP/MNP (0090) with UFO fuel map (0092).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0090_invest_opendata_verification"),
        ("delayu", "0092_fuel_ufo_report_phone"),
    ]

    operations = []
