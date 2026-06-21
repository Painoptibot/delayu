"""M36 — регламентные сроки."""
from datetime import timedelta

from django.utils import timezone

from delayu.models import CaseFile, CaseRegulation


def filter_regulations(subsystem, *, active_only=False):
    qs = CaseRegulation.objects.filter(subsystem=subsystem)
    if active_only:
        qs = qs.filter(is_active=True)
    return qs.order_by("code")


def apply_regulation_to_case(case: CaseFile, regulation: CaseRegulation):
    if regulation.applies_on_status and case.status != regulation.applies_on_status:
        return False
    case.due_date = timezone.now().date() + timedelta(days=regulation.default_working_days)
    case.save(update_fields=["due_date"])
    return True
