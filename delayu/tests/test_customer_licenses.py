"""Выдача лицензий заказчикам и мест пользователям."""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from delayu.models import CustomerLicense, Organization, Role, Subsystem, SubsystemMembership
from delayu.services.licenses import LicenseError, assign_seat, issue_license, release_seat

User = get_user_model()


class CustomerLicenseTests(TestCase):
    def setUp(self):
        self.sub = Subsystem.objects.create(code="lic", name="Лицензии", status="active")
        self.org = Organization.objects.create(subsystem=self.sub, code="cust", name="Заказчик")
        self.other = Organization.objects.create(subsystem=self.sub, code="other", name="Другой")
        self.role = Role.objects.create(subsystem=self.sub, code="user", name="Пользователь")
        self.admin = User.objects.create_user(username="issuer", password="x", is_superuser=True)
        self.user = User.objects.create_user(username="seat", password="x")
        self.outsider = User.objects.create_user(username="out", password="x")
        SubsystemMembership.objects.create(
            user=self.admin, subsystem=self.sub, organization=self.org, role=self.role, is_default=True
        )
        SubsystemMembership.objects.create(
            user=self.user, subsystem=self.sub, organization=self.org, role=self.role
        )
        SubsystemMembership.objects.create(
            user=self.outsider, subsystem=self.sub, organization=self.other, role=self.role
        )

    def _issue(self, seats=1):
        return issue_license(
            subsystem=self.sub,
            organization=self.org,
            title="Платформа",
            seats=seats,
            valid_from=date.today(),
            valid_until=date.today() + timedelta(days=365),
            support_until=date.today() + timedelta(days=365),
            note="",
            modules=[],
            issued_by=self.admin,
        )

    def test_issue_and_assign_seat(self):
        lic = self._issue()
        self.assertTrue(lic.number.startswith("DL-"))
        seat = assign_seat(lic, self.user, self.admin)
        self.assertEqual(seat.user, self.user)
        with self.assertRaises(LicenseError):
            assign_seat(lic, self.user, self.admin)
        with self.assertRaises(LicenseError):
            assign_seat(lic, self.outsider, self.admin)

    def test_seat_limit_and_release(self):
        lic = self._issue(seats=1)
        assign_seat(lic, self.user, self.admin)
        extra = User.objects.create_user(username="extra", password="x")
        SubsystemMembership.objects.create(
            user=extra, subsystem=self.sub, organization=self.org, role=self.role
        )
        with self.assertRaises(LicenseError):
            assign_seat(lic, extra, self.admin)
        release_seat(lic, lic.seat_assignments.get().pk)
        assign_seat(lic, extra, self.admin)
        self.assertEqual(lic.seat_assignments.count(), 1)

    def test_suspended_license_blocks_seat(self):
        lic = self._issue()
        lic.status = CustomerLicense.Status.SUSPENDED
        lic.save(update_fields=["status"])
        with self.assertRaises(LicenseError):
            assign_seat(lic, self.user, self.admin)

    def test_pages_render(self):
        lic = self._issue()
        client = Client()
        client.force_login(self.admin)
        host = {"HTTP_HOST": "127.0.0.1"}
        self.assertEqual(client.get("/ux/licenses/", **host).status_code, 200)
        self.assertEqual(client.get("/ux/licenses/new/", **host).status_code, 200)
        detail = client.get(f"/ux/licenses/{lic.pk}/", **host)
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, lic.number)
        self.assertContains(detail, "lic-cert")
        self.assertContains(detail, "Действует")
        listing = client.get("/ux/licenses/", **host)
        self.assertContains(listing, "lic-board")
        self.assertContains(listing, lic.number)
        self.assertContains(listing, "2 / 1")
        self.assertContains(detail, "issuer")
        self.assertContains(detail, "seat")
        self.assertNotContains(detail, ">out<")
        self.assertContains(detail, "пользователей больше, чем мест")
