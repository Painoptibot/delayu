"""Централизованная нумерация регистрационных записей (#9)."""
import re

from django.db import transaction
from django.utils import timezone

from delayu.models import Correspondence


@transaction.atomic
def next_reg_number(subsystem, direction: str, *, prefix_map=None) -> str:
    prefix_map = prefix_map or {
        Correspondence.Direction.IN: "ВХ",
        Correspondence.Direction.OUT: "ИСХ",
    }
    prefix = prefix_map.get(direction, "РЕГ")
    year = timezone.now().year
    base = f"{prefix}-{year}-"
    last = (
        Correspondence.objects.select_for_update()
        .filter(subsystem=subsystem, direction=direction, reg_number__startswith=base)
        .order_by("-reg_number")
        .first()
    )
    n = 1
    if last:
        m = re.search(r"-(\d+)$", last.reg_number)
        if m:
            n = int(m.group(1)) + 1
    return f"{base}{n:04d}"
