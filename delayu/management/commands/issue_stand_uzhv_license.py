"""Лицензия УЖВ только для стенда delau.tech. На сервере заказчика не запускать."""
from datetime import date

from django.core.management.base import BaseCommand

from delayu.models import CustomerLicense, Organization, Subsystem
from delayu.services.licenses import issue_license


class Command(BaseCommand):
    help = "Выдаёт лицензию контура УЖВ на стенде, если её ещё нет."

    def handle(self, *args, **options):
        subsystem = Subsystem.objects.filter(code="uzhv").first()
        if not subsystem:
            self.stdout.write("subsystem uzhv not found")
            return
        existing = CustomerLicense.objects.filter(subsystem=subsystem).order_by("id").first()
        if existing:
            self.stdout.write(f"exists {existing.number} from {existing.valid_from}")
            return
        organization = Organization.objects.filter(subsystem=subsystem, code="uzhv").first()
        if organization is None:
            organization = (
                Organization.objects.filter(subsystem=subsystem, is_active=True).order_by("id").first()
            )
        if organization is None:
            self.stdout.write("organization not found")
            return
        license_row = issue_license(
            subsystem=subsystem,
            organization=organization,
            title="Неисключительная лицензия на программу «ДелаЮ», контур АИС УЖВ",
            seats=50,
            valid_from=date(2026, 10, 18),
            valid_until=None,
            support_until=None,
            note="Стенд delau.tech. На боевой сервер заказчика не переносилась.",
            modules=[],
            issued_by=None,
        )
        self.stdout.write(
            f"issued {license_row.number} from {license_row.valid_from} "
            f"seats={license_row.seats} org={organization.name}"
        )
