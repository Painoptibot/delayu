"""Соединяет лицензии заказчика с уже выложенным чатом поддержки УЖВ."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0096_contour_delivery"),
        ("delayu", "0100_uzhv_support_chat"),
    ]

    operations = []
