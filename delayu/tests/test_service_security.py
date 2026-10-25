"""Границы доступа сервисного контура: чужой контур, файл, дата, CSRF."""
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from delayu.models import (
    ModuleCatalog,
    Organization,
    Role,
    RoleModulePermission,
    Subsystem,
    SubsystemMembership,
    SubsystemModule,
)
from delayu.models_service import (
    ServiceChecklist,
    ServiceCheckMark,
    ServiceCustomer,
    ServiceDeal,
    ServiceMedia,
    ServicePlaybook,
)
from delayu.services.service_process import ensure_process

User = get_user_model()


def _grant(subsystem, role):
    for code, name in (("S01", "Карточка"), ("S02", "Объекты")):
        module, _created = ModuleCatalog.objects.get_or_create(code=code, defaults={"name": name})
        SubsystemModule.objects.create(subsystem=subsystem, module=module, enabled=True)
        RoleModulePermission.objects.create(role=role, module=module, can_view=True)


class ServiceSecurityTests(TestCase):
    def setUp(self):
        self.sub = Subsystem.objects.create(
            code="svc-sec", name="Сервис", status="active", industry_template="service"
        )
        self.other = Subsystem.objects.create(
            code="other-sec", name="Чужой", status="active", industry_template="service"
        )
        self.uzhv = Subsystem.objects.create(
            code="uzhv-sec", name="УЖВ", status="active", industry_template="uzhv"
        )
        org = Organization.objects.create(subsystem=self.sub, code="org", name="Орг")
        role = Role.objects.create(subsystem=self.sub, code="clerk", name="Оператор")
        _grant(self.sub, role)
        self.user = User.objects.create_user("svc_sec", password="svc-pass")
        SubsystemMembership.objects.create(
            user=self.user, subsystem=self.sub, organization=org, role=role, is_default=True
        )
        self.customer = ServiceCustomer.objects.create(
            subsystem=self.sub, number="ZK-0001", display_name="Северная башня", phone="+15870001122"
        )
        self.foreign = ServiceCustomer.objects.create(
            subsystem=self.other, number="ZK-9000", display_name="Чужая башня", phone="+15870009999"
        )
        self.client.login(username="svc_sec", password="svc-pass")

    def test_anonymous_and_other_contour_cannot_open_the_service(self):
        self.client.logout()
        anonymous = self.client.get(reverse("service-playbooks"))
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn("/auth/login/", anonymous.url)
        stranger = User.objects.create_user("uzhv_sec", password="svc-pass")
        org = Organization.objects.create(subsystem=self.uzhv, code="u", name="У")
        role = Role.objects.create(subsystem=self.uzhv, code="clerk", name="Оператор")
        SubsystemMembership.objects.create(
            user=stranger, subsystem=self.uzhv, organization=org, role=role, is_default=True
        )
        self.client.login(username="uzhv_sec", password="svc-pass")
        denied = self.client.get(reverse("service-playbooks"))
        self.assertEqual(denied.status_code, 403)

    def test_customer_of_another_contour_stays_closed(self):
        page = self.client.get(reverse("service-customer", args=[self.foreign.pk]))
        self.assertEqual(page.status_code, 404)
        merged = self.client.post(
            reverse("service-customer", args=[self.customer.pk]),
            {"action": "merge", "other_id": self.foreign.pk},
        )
        self.assertEqual(merged.status_code, 404)
        self.foreign.refresh_from_db()
        self.assertEqual(self.foreign.display_name, "Чужая башня")

    def test_checklist_from_another_playbook_is_not_applied(self):
        ensure_process(self.other)
        foreign_item = ServiceChecklist.objects.filter(playbook__subsystem=self.other).first()
        self.assertIsNotNone(foreign_item)
        deal = ServiceDeal.objects.create(
            subsystem=self.sub,
            customer=self.customer,
            number="DL-0001",
            title="Стена",
            job_type=foreign_item.playbook.job_type,
        )
        response = self.client.post(
            reverse("service-customer", args=[self.customer.pk]),
            {"action": "check", "deal_id": deal.pk, "item_id": foreign_item.pk},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ServiceCheckMark.objects.filter(deal=deal, item=foreign_item).exists())

    def test_media_rejects_html_and_hides_another_contour_file(self):
        upload = SimpleUploadedFile("page.html", b"<script>alert(1)</script>", content_type="text/html")
        response = self.client.post(
            reverse("service-media"),
            {"folder": "x", "title": "Страница", "kind": "file", "note": "", "file": upload},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ServiceMedia.objects.filter(title="Страница").exists())
        hidden = ServiceMedia.objects.create(subsystem=self.other, folder="x", title="Чужой файл", kind="file")
        missing = self.client.post(
            reverse("service-media"),
            {"form_action": "delete", "media_id": hidden.pk},
        )
        self.assertEqual(missing.status_code, 404)
        self.assertTrue(ServiceMedia.objects.filter(pk=hidden.pk).exists())

    def test_bad_next_date_does_not_crash(self):
        deal = ServiceDeal.objects.create(
            subsystem=self.sub, customer=self.customer, number="DL-0002", title="Дата", job_type="sale"
        )
        response = self.client.post(
            reverse("service-customer", args=[self.customer.pk]),
            {"action": "next", "deal_id": deal.pk, "next_on": "вчера"},
        )
        self.assertEqual(response.status_code, 302)
        deal.refresh_from_db()
        self.assertIsNone(deal.next_on)

    def test_post_without_csrf_is_rejected(self):
        client = Client(enforce_csrf_checks=True)
        client.login(username="svc_sec", password="svc-pass")
        response = client.post(reverse("service-playbooks"), {"action": "type", "code": "hack", "title": "Hack"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ServicePlaybook.objects.filter(job_type="hack").exists())

    def test_uploaded_media_is_not_a_public_url(self):
        self.client.logout()
        response = self.client.get("/media/service-media/page.html")
        self.assertEqual(response.status_code, 404)
