"""Карточка заказчика, агент и затраты на объект."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from delayu.menu import build_menu_for_membership
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
    ServiceChannel,
    ServiceCustomer,
    ServiceDeployment,
    ServiceMessage,
    ServiceObject,
    ServiceVisit,
)
from delayu.services.service_agent import answer_question, compose_payment
from delayu.services.service_dialogue import ServiceFlowError, post_message, release_due

User = get_user_model()


class ServiceContourTests(TestCase):
    def setUp(self):
        self.sub = Subsystem.objects.create(
            code="svc", name="Сервис", status="active", industry_template="service"
        )
        self.other = Subsystem.objects.create(
            code="other", name="Чужой", status="active", industry_template="uzhv"
        )
        self.org = Organization.objects.create(subsystem=self.sub, code="org", name="Орг")
        self.role = Role.objects.create(subsystem=self.sub, code="clerk", name="Оператор")
        for code, name in (("S01", "Карточка"), ("S02", "Объекты")):
            module, _created = ModuleCatalog.objects.get_or_create(
                code=code, defaults={"name": name}
            )
            SubsystemModule.objects.create(subsystem=self.sub, module=module, enabled=True)
            RoleModulePermission.objects.create(role=self.role, module=module, can_view=True)
        self.user = User.objects.create_user("svc_op", password="svc-pass")
        self.membership = SubsystemMembership.objects.create(
            user=self.user,
            subsystem=self.sub,
            organization=self.org,
            role=self.role,
            is_default=True,
        )
        self.customer = ServiceCustomer.objects.create(
            subsystem=self.sub,
            number="ZK-0001",
            display_name="Северная башня",
            phone="+79990001122",
            stage=ServiceCustomer.Stage.SETUP,
            payment_state=ServiceCustomer.PaymentState.INVOICED,
            invoice_amount=Decimal("150000.00"),
        )
        self.client.login(username="svc_op", password="svc-pass")

    def test_menu_shows_customer_card(self):
        labels = [
            item["name"]
            for item in build_menu_for_membership(self.membership)
            if item.get("name")
        ]
        self.assertIn("Заказчики", labels)
        self.assertIn("Воронка", labels)
        self.assertIn("Заявки", labels)
        self.assertIn("Объекты", labels)
        from delayu.services.service_channels import CHANNEL_CODES

        self.assertNotIn("max", CHANNEL_CODES)
        self.assertNotIn("viber", CHANNEL_CODES)
        self.assertIn("sms", CHANNEL_CODES)
        self.assertIn("google", CHANNEL_CODES)

    def test_question_and_stage_share_one_card(self):
        self.client.post(
            reverse("service-customer", args=[self.customer.pk]),
            {"action": "ask", "channel": "whatsapp", "body": "Какой этап работ?"},
        )
        self.client.post(
            reverse("service-customer", args=[self.customer.pk]),
            {"action": "inbound", "channel": "sms", "body": "Мы на объекте"},
        )
        kinds = list(
            self.customer.messages.order_by("pk").values_list("channel", "author_kind", "kind")
        )
        self.assertEqual(
            kinds,
            [
                ("whatsapp", "customer", "dialogue"),
                ("whatsapp", "agent", "answer"),
                ("sms", "customer", "dialogue"),
            ],
        )
        answer = self.customer.messages.get(kind="answer").body
        self.assertIn("equipment setup", answer)
        self.assertNotIn("150000", answer)

    def test_payment_notice_waits_for_its_time_then_uses_the_card(self):
        from delayu.services.service_agent import queue_notice

        later = timezone.now() + timedelta(hours=2)
        queue_notice(
            customer=self.customer,
            channel="sms",
            kind="payment",
            scheduled_for=later,
            user=self.user,
        )
        message = self.customer.messages.get()
        self.assertEqual(message.status, ServiceMessage.Status.SCHEDULED)
        self.assertEqual(release_due(self.sub, now=timezone.now()), 0)
        self.customer.payment_state = ServiceCustomer.PaymentState.PAID
        self.customer.save(update_fields=["payment_state"])
        self.assertEqual(release_due(self.sub, now=later + timedelta(minutes=1)), 1)
        message.refresh_from_db()
        self.assertEqual(message.status, ServiceMessage.Status.SENT)
        self.assertIn("paid", message.body)
        self.assertIn("150000.00", message.body)

    def test_paused_channel_keeps_the_notice_out(self):
        from delayu.services.service_channels import ensure_channels

        ensure_channels(self.sub)
        ServiceChannel.objects.filter(subsystem=self.sub, code="sms").update(
            status=ServiceChannel.Status.PAUSED
        )
        with self.assertRaises(ServiceFlowError):
            post_message(
                customer=self.customer,
                channel="sms",
                direction="out",
                author_kind="agent",
                body="Этап: работы.",
                kind="stage",
            )

    def test_visit_and_forces_roll_into_the_object(self):
        site = ServiceObject.objects.create(
            subsystem=self.sub,
            customer=self.customer,
            code="OB-0001",
            title="Кровля",
            stage=ServiceCustomer.Stage.SETUP,
        )
        ServiceVisit.objects.create(
            subsystem=self.sub,
            site=site,
            employee=self.user,
            departed_on=timezone.localdate(),
            distance_mi=Decimal("12.5"),
            rate_per_mile=Decimal("40"),
            hours=Decimal("3"),
            hour_rate=Decimal("500"),
            other_cost=Decimal("100"),
        )
        ServiceDeployment.objects.create(
            subsystem=self.sub,
            site=site,
            kind=ServiceDeployment.Kind.PEOPLE,
            title="Монтажники",
            quantity=Decimal("2"),
            unit="чел",
            unit_cost=Decimal("8000"),
        )
        visit = site.visits.get()
        self.assertEqual(visit.travel_cost, Decimal("500.00"))
        self.assertEqual(visit.labor_cost, Decimal("1500.00"))
        self.assertEqual(visit.total_cost, Decimal("2100.00"))
        self.assertEqual(site.deployments.get().total_cost, Decimal("16000.00"))
        response = self.client.get(reverse("service-object", args=[site.pk]))
        self.assertContains(response, "18100,00")
        self.assertIn("18100.00", answer_question(self.customer, "какие затраты на выезды"))

    def test_payment_text_says_when_the_invoice_is_missing(self):
        self.customer.invoice_amount = None
        self.customer.save(update_fields=["invoice_amount"])
        text = compose_payment(self.customer)
        self.assertIn("not on the card", text)
        self.assertNotIn("150000", text)

    def test_foreign_contour_does_not_open_the_card(self):
        role = Role.objects.create(subsystem=self.other, code="clerk", name="Чужой")
        org = Organization.objects.create(subsystem=self.other, code="org", name="Чужой")
        module = ModuleCatalog.objects.get(code="S01")
        SubsystemModule.objects.create(subsystem=self.other, module=module, enabled=True)
        RoleModulePermission.objects.create(role=role, module=module, can_view=True)
        user = User.objects.create_user("foreign", password="svc-pass")
        SubsystemMembership.objects.create(
            user=user, subsystem=self.other, organization=org, role=role, is_default=True
        )
        self.client.logout()
        self.client.login(username="foreign", password="svc-pass")
        response = self.client.get(reverse("service-hub"))
        self.assertEqual(response.status_code, 403)

    def test_new_customer_lands_on_the_led_sales_board(self):
        self.client.post(
            reverse("service-customers"),
            {
                "display_name": "Calgary Church",
                "stage": "new_lead",
                "payment_state": "none",
            },
        )
        from delayu.models_service import ServiceDeal

        deal = ServiceDeal.objects.get(title="Calgary Church")
        self.assertEqual(deal.stage, "new_lead")
        self.assertEqual(deal.customer.stage, "new_lead")
        moved = self.client.post(
            reverse("service-deals"),
            {"action": "move", "deal_id": deal.pk, "stage": "qualified"},
        )
        self.assertEqual(moved.status_code, 302)
        deal.refresh_from_db()
        deal.customer.refresh_from_db()
        self.assertEqual(deal.stage, "qualified")
        self.assertEqual(deal.customer.stage, "qualified")
        board = self.client.get(reverse("service-deals"))
        self.assertContains(board, "Calgary Church")
        self.assertContains(board, "Qualified")
        self.assertTrue(
            deal.customer.messages.filter(kind="stage", status="sent", body__icontains="qualified").exists()
        )

    def test_sale_quote_qualifies_and_schedules_followups(self):
        response = self.client.post(
            reverse("service-quotes"),
            {
                "kind": "sale",
                "display_name": "Grace Chapel",
                "email": "grace@example.com",
                "phone": "+1 403 555 0100",
                "city": "Calgary",
                "state": "AB",
                "timeline": "this spring",
                "decision_maker": "yes",
                "screen_over_30": "yes",
                "church_project": "yes",
                "send_catalog": "on",
                "message": "Need a sanctuary wall",
            },
        )
        self.assertEqual(response.status_code, 302)
        from delayu.models_service import ServiceDeal

        deal = ServiceDeal.objects.get(title="Grace Chapel")
        self.assertEqual(deal.stage, "qualified")
        self.assertEqual(deal.job_type, "sale")
        self.assertEqual(deal.source, "Website — SALES Quote")
        self.assertIn("church", deal.customer.tags)
        bodies = " ".join(deal.customer.messages.values_list("body", flat=True))
        self.assertIn("Catalog:", bodies)
        self.assertIn("Church LED:", bodies)
        self.assertIn("Province follow-up:", bodies)
        self.assertIn("AB", bodies)
        self.assertTrue(deal.customer.messages.filter(kind="stage", status="scheduled").exists())

    def test_rental_quote_without_size_stays_a_new_lead_until_rules_pass(self):
        self.client.post(
            reverse("service-quotes"),
            {
                "kind": "rental",
                "display_name": "Arena Night",
                "location": "Toronto, ON",
                "guests_over_200": "no",
                "church_project": "unknown",
                "event_on": "2026-11-02",
            },
        )
        from delayu.models_service import ServiceDeal

        deal = ServiceDeal.objects.get(title="Arena Night")
        self.assertEqual(deal.job_type, "rental")
        self.assertEqual(deal.stage, "new_lead")
        self.assertIn("QC", deal.qualification)
        deal.guests_over_200 = "yes"
        deal.state = "QC"
        deal.save(update_fields=["guests_over_200", "state"])
        from delayu.services.service_automation import qualify_deal

        qualify_deal(deal)
        deal.refresh_from_db()
        self.assertEqual(deal.stage, "qualified")

    def test_inbound_sms_finds_the_card_or_opens_a_lead(self):
        self.customer.phone = "+1 825-258-5393"
        self.customer.save(update_fields=["phone"])
        found = self.client.post(
            reverse("service-channels"),
            {"action": "inbound", "channel": "sms", "address": "8252585393", "body": "We need a wall"},
        )
        self.assertEqual(found.status_code, 302)
        self.assertTrue(self.customer.messages.filter(body="We need a wall", direction="in").exists())
        opened = self.client.post(
            reverse("service-channels"),
            {
                "action": "inbound",
                "channel": "whatsapp",
                "address": "+1 403 555 0199",
                "body": "Renting for Friday",
            },
        )
        self.assertEqual(opened.status_code, 302)
        from delayu.models_service import ServiceCustomer

        fresh = ServiceCustomer.objects.get(phone="+1 403 555 0199")
        self.assertEqual(fresh.stage, "new_lead")
        self.assertEqual(fresh.deals.get().source, "whatsapp")

    def test_calendars_workflows_funnels_mail_ads_invoices_and_media(self):
        from delayu.models_service import ServiceAd, ServiceCustomer, ServiceMedia
        from delayu.services.service_deals import create_deal
        from delayu.services.service_office import ensure_calendars

        deal = create_deal(customer=self.customer, title="Consultation", stage="qualified")
        calendar = ensure_calendars(self.sub).get(name="LED Screen Project Consultation")
        booked = self.client.post(
            reverse("service-calendars"),
            {
                "calendar": calendar.pk,
                "customer": self.customer.pk,
                "starts_at": "2026-11-02T15:00",
                "note": "online",
            },
        )
        self.assertEqual(booked.status_code, 302)
        deal.refresh_from_db()
        self.assertEqual(deal.stage, "meeting")
        workflows = self.client.get(reverse("service-workflows"))
        self.assertContains(workflows, "SLA Timer")
        funnels = self.client.get(reverse("service-funnels"))
        self.assertContains(funnels, "SALES Quote — WP Website")
        self.customer.tags = "church"
        self.customer.save(update_fields=["tags"])
        mailed = self.client.post(
            reverse("service-mailings"),
            {"subject": "How to choose", "audience": "church", "body": "Size and brightness."},
        )
        self.assertEqual(mailed.status_code, 302)
        self.assertTrue(self.customer.messages.filter(channel="email", body__icontains="How to choose").exists())
        self.client.post(
            reverse("service-ads"),
            {"name": "Search AB", "network": "Google", "province": "AB", "job_type": "sale"},
        )
        ad = ServiceAd.objects.get(name="Search AB")
        lead = self.client.post(
            reverse("service-ads"),
            {"action": "lead", "ad": ad.pk, "display_name": "Banner Lead", "phone": "+1 403 555 0177"},
        )
        self.assertEqual(lead.status_code, 302)
        banner = ServiceCustomer.objects.get(display_name="Banner Lead")
        self.assertIn("Google", banner.deals.get().source)
        self.assertEqual(banner.state, "AB")
        invoiced = self.client.post(
            reverse("service-invoices"),
            {
                "customer": self.customer.pk,
                "title": "LED wall",
                "amount": "12000.00",
                "status": "sent",
            },
        )
        self.assertEqual(invoiced.status_code, 302)
        self.customer.refresh_from_db()
        deal.refresh_from_db()
        self.assertEqual(self.customer.payment_state, "invoiced")
        self.assertEqual(deal.stage, "invoice")
        stored = self.client.post(
            reverse("service-media"),
            {"folder": "Churches", "title": "Sanctuary wall", "kind": "video", "note": "install"},
        )
        self.assertEqual(stored.status_code, 302)
        self.assertTrue(ServiceMedia.objects.filter(title="Sanctuary wall", folder="Churches").exists())

    def test_seeded_rows_can_be_edited_and_new_ones_added(self):
        from delayu.models_service import ServiceCalendar, ServiceInvoice, ServiceMedia
        from delayu.services.service_automation import ensure_workflows
        from delayu.services.service_channels import ensure_channels
        from delayu.services.service_deals import create_deal
        from delayu.services.service_office import ensure_calendars, ensure_funnels

        channel = ensure_channels(self.sub).get(code="sms")
        saved = self.client.post(
            reverse("service-channels"),
            {
                "form_action": "save",
                "channel_id": channel.pk,
                f"ch{channel.pk}-title": "Text line",
                f"ch{channel.pk}-detail": "Customer SMS",
            },
        )
        self.assertEqual(saved.status_code, 302)
        ensure_channels(self.sub)
        channel.refresh_from_db()
        self.assertEqual(channel.title, "Text line")
        created = self.client.post(
            reverse("service-channels"),
            {
                "form_action": "create",
                "newch-title": "Yard line",
                "newch-detail": "Jobsite radio",
                "newch-code": "yard",
            },
        )
        self.assertEqual(created.status_code, 302)
        self.assertTrue(ServiceChannel.objects.filter(subsystem=self.sub, code="yard").exists())

        calendar = ensure_calendars(self.sub).get(name="Omni LED Interview")
        self.client.post(
            reverse("service-calendars"),
            {
                "form_action": "save_calendar",
                "calendar_id": calendar.pk,
                f"c{calendar.pk}-name": "Omni LED Interview",
                f"c{calendar.pk}-kind": "meeting",
                f"c{calendar.pk}-minutes": "45",
                f"c{calendar.pk}-owner_name": "Vitaly",
                f"c{calendar.pk}-active": "on",
            },
        )
        calendar.refresh_from_db()
        self.assertEqual(calendar.minutes, 45)
        self.assertEqual(calendar.owner_name, "Vitaly")
        self.client.post(
            reverse("service-calendars"),
            {
                "form_action": "create_calendar",
                "newcal-name": "Evening consult",
                "newcal-kind": "meeting",
                "newcal-minutes": "30",
                "newcal-owner_name": "Alina",
                "newcal-active": "on",
            },
        )
        self.assertTrue(ServiceCalendar.objects.filter(subsystem=self.sub, name="Evening consult").exists())

        workflow = ensure_workflows(self.sub).get(code="first-response")
        self.client.post(
            reverse("service-workflows"),
            {
                "form_action": "save",
                "workflow_id": workflow.pk,
                f"w{workflow.pk}-name": "SLA Timer renamed",
                f"w{workflow.pk}-folder": workflow.folder,
                f"w{workflow.pk}-trigger": workflow.trigger,
                f"w{workflow.pk}-action": workflow.action,
            },
        )
        workflow.refresh_from_db()
        self.assertEqual(workflow.name, "SLA Timer renamed")

        funnel = ensure_funnels(self.sub).get(name="SALES Quote — WP Website")
        self.client.post(
            reverse("service-funnels"),
            {
                "form_action": "save",
                "funnel_id": funnel.pk,
                f"fn{funnel.pk}-name": funnel.name,
                f"fn{funnel.pk}-steps": "Updated steps",
                f"fn{funnel.pk}-status": "active",
            },
        )
        funnel.refresh_from_db()
        self.assertEqual(funnel.steps, "Updated steps")

        deal = create_deal(customer=self.customer, title="Wall", stage="new_lead")
        self.client.post(
            reverse("service-deals"),
            {
                "action": "edit",
                "deal_id": deal.pk,
                f"d{deal.pk}-title": "Updated wall",
                f"d{deal.pk}-stage": "qualified",
                f"d{deal.pk}-job_type": "sale",
                f"d{deal.pk}-placement": "indoor",
                f"d{deal.pk}-decision_maker": "yes",
                f"d{deal.pk}-screen_over_30": "yes",
                f"d{deal.pk}-guests_over_200": "unknown",
                f"d{deal.pk}-church_project": "no",
                f"d{deal.pk}-state": "AB",
            },
        )
        deal.refresh_from_db()
        self.assertEqual(deal.title, "Updated wall")
        self.assertEqual(deal.stage, "qualified")

        self.client.post(
            reverse("service-invoices"),
            {"customer": self.customer.pk, "title": "Draft wall", "amount": "500.00", "status": "draft"},
        )
        invoice = ServiceInvoice.objects.get(title="Draft wall")
        self.client.post(
            reverse("service-invoices"),
            {
                "form_action": "save",
                "invoice_id": invoice.pk,
                f"i{invoice.pk}-customer": self.customer.pk,
                f"i{invoice.pk}-title": "Draft wall",
                f"i{invoice.pk}-amount": "500.00",
                f"i{invoice.pk}-status": "paid",
            },
        )
        invoice.refresh_from_db()
        self.customer.refresh_from_db()
        self.assertEqual(invoice.status, "paid")
        self.assertEqual(self.customer.payment_state, "paid")

        self.client.post(
            reverse("service-media"),
            {"folder": "Arenas", "title": "Ice wall", "kind": "image", "note": ""},
        )
        media = ServiceMedia.objects.get(title="Ice wall")
        self.client.post(
            reverse("service-media"),
            {
                "form_action": "save",
                "media_id": media.pk,
                f"m{media.pk}-folder": "Arenas",
                f"m{media.pk}-title": "Ice wall night",
                f"m{media.pk}-kind": "image",
                f"m{media.pk}-note": "retake",
            },
        )
        media.refresh_from_db()
        self.assertEqual(media.title, "Ice wall night")
        self.assertEqual(media.note, "retake")

    def test_canadian_led_snapshot_lands_in_the_contour(self):
        fields = self.client.get(reverse("service-fields"))
        self.assertContains(fields, "Decision Maker?")
        self.assertContains(fields, "Guests Over 200?")
        workflows = self.client.get(reverse("service-workflows"))
        self.assertContains(workflows, "GOOGLE CA")
        self.assertContains(workflows, "Church Nurture Email")
        forms = self.client.get(reverse("service-forms"))
        self.assertContains(forms, "SALES Quote - WP Website (Organic)")
        phones = self.client.get(reverse("service-phones"))
        self.assertContains(phones, "CL - General")
        self.assertContains(phones, "Владимир Ху")
        self.assertContains(phones, "Виталий Кочанов")
        self.assertContains(phones, "237779@list.ru")
        hub = self.client.get(reverse("service-hub"))
        self.assertContains(hub, "https://vikonn.com/")
        self.assertContains(hub, "остаётся в HighLevel")
        funnels = self.client.get(reverse("service-funnels"))
        self.assertContains(funnels, "VIKONN")
        ads = self.client.get(reverse("service-ads"))
        self.assertContains(ads, "GOOGLE ALBERTA")

    def test_form_opens_a_lead_and_the_inbox_shows_the_task(self):
        from delayu.models_service import ServiceForm, ServiceTask
        from delayu.services.service_dialogue import post_message
        from delayu.services.service_snapshot import load_forms

        load_forms(self.sub)
        form = ServiceForm.objects.get(subsystem=self.sub, name="RENTAL Quote - WP Website (Organic)")
        opened = self.client.post(
            reverse("service-forms"),
            {"form_id": form.pk, "display_name": "Arena Night", "phone": "+1 403 555 0101", "message": "Saturday"},
        )
        self.assertEqual(opened.status_code, 302)
        from delayu.models_service import ServiceCustomer

        lead = ServiceCustomer.objects.get(display_name="Arena Night")
        self.assertEqual(lead.deals.get().source, form.name)
        self.assertEqual(lead.deals.get().job_type, "rental")
        posted = self.client.post(
            reverse("service-customer", args=[self.customer.pk]),
            {"action": "task", "title": "Call back", "due_on": "2026-11-03", "note": "after quote"},
        )
        self.assertEqual(posted.status_code, 302)
        task = ServiceTask.objects.get(title="Call back")
        self.assertEqual(task.customer, self.customer)
        post_message(
            customer=self.customer,
            channel="sms",
            direction="in",
            author_kind="customer",
            body="Can we talk tomorrow?",
        )
        inbox = self.client.get(reverse("service-inbox"))
        self.assertContains(inbox, "Can we talk tomorrow?")
        report = self.client.get(reverse("service-report"))
        self.assertContains(report, "New Lead")
        self.assertContains(report, "Открытые задачи")

    def test_playbook_gates_queue_and_the_same_customer_card(self):
        from delayu.models_service import ServiceAudit, ServiceCrewLine, ServiceDeal, ServiceMedia

        page = self.client.get(reverse("service-playbooks"))
        self.assertContains(page, "Продажа экрана")
        self.assertContains(page, "миля")
        added = self.client.post(
            reverse("service-playbooks"),
            {"action": "type", "code": "modules", "title": "Сервис модулей"},
        )
        self.assertEqual(added.status_code, 302)
        opened = self.client.post(
            reverse("service-playbooks"),
            {
                "action": "deal",
                "customer": self.customer.pk,
                "job_type": "modules",
                "title": "Module wall",
            },
        )
        self.assertEqual(opened.status_code, 302)
        self.assertEqual(self.customer.deals.count(), 1)
        deal = ServiceDeal.objects.get(title="Module wall")
        self.assertEqual(deal.stage, "new_lead")
        blocked = self.client.post(
            reverse("service-customer", args=[self.customer.pk]),
            {"action": "advance", "deal_id": deal.pk, "stage": "qualified"},
        )
        self.assertEqual(blocked.status_code, 302)
        deal.refresh_from_db()
        self.assertEqual(deal.stage, "new_lead")
        deal.state = "AB"
        deal.save(update_fields=["state"])
        passed = self.client.post(
            reverse("service-customer", args=[self.customer.pk]),
            {"action": "advance", "deal_id": deal.pk, "stage": "qualified"},
        )
        self.assertEqual(passed.status_code, 302)
        deal.refresh_from_db()
        self.assertEqual(deal.stage, "qualified")
        self.assertTrue(ServiceAudit.objects.filter(deal=deal, action="стадия").exists())
        repeated = self.client.post(
            reverse("service-customer", args=[self.customer.pk]),
            {"action": "repeat", "deal_id": deal.pk},
        )
        self.assertEqual(repeated.status_code, 302)
        self.assertEqual(ServiceDeal.objects.filter(customer=self.customer).count(), 2)
        self.assertEqual(ServiceCustomer.objects.filter(display_name="Северная башня").count(), 1)
        fresh = ServiceDeal.objects.get(title="Module wall повтор")
        self.assertEqual(fresh.state, "AB")
        self.client.post(
            reverse("service-customer", args=[self.customer.pk]),
            {
                "action": "owner",
                "deal_id": fresh.pk,
                "owner_name": "Artur",
                "observers": "Vitaly",
            },
        )
        fresh.refresh_from_db()
        self.assertEqual(fresh.owner_name, "Artur")
        deal.created_at = timezone.now() - timedelta(hours=3)
        deal.stage = "new_lead"
        deal.status = "open"
        deal.paused = False
        deal.owner_name = ""
        deal.save()
        queue = self.client.get(reverse("service-queue"))
        self.assertContains(queue, deal.number)
        self.client.post(
            reverse("service-customer", args=[self.customer.pk]),
            {"action": "pause", "deal_id": deal.pk, "pause_reason": "Ждём заказчика"},
        )
        deal.refresh_from_db()
        self.assertTrue(deal.paused)
        paused = self.client.get(reverse("service-queue"))
        self.assertContains(paused, "Ждём заказчика")
        from delayu.services.service_process import sla_missed

        self.assertNotIn(deal.pk, [row.pk for row in sla_missed(self.sub)])
        site = ServiceObject.objects.create(
            subsystem=self.sub, customer=self.customer, code="ST-1", title="Arena floor"
        )
        sales = self.client.get(reverse("service-queue") + "?role=sales")
        self.assertNotContains(sales, site.code)
        dispatcher = self.client.get(reverse("service-queue") + "?role=dispatcher")
        self.assertContains(dispatcher, site.code)
        self.client.post(
            reverse("service-customer", args=[self.customer.pk]),
            {"action": "contact", "name": "Pastor Jon", "role_name": "Buyer", "decides": "on"},
        )
        card = self.client.get(reverse("service-customer", args=[self.customer.pk]))
        self.assertContains(card, "Pastor Jon")
        self.assertContains(card, "Хронология")
        self.client.post(
            reverse("service-customer", args=[self.customer.pk]),
            {
                "action": "crew",
                "deal_id": fresh.pk,
                "crew_title": "Riggers",
                "planned": "4",
                "actual": "2",
                "unit": "чел",
            },
        )
        line = ServiceCrewLine.objects.get(title="Riggers")
        self.assertEqual(line.planned, Decimal("4"))
        self.assertEqual(line.actual, Decimal("2"))
        self.client.post(
            reverse("service-media"),
            {
                "folder": "Modules",
                "title": "Module night",
                "kind": "image",
                "note": "",
                "deal": fresh.pk,
                "job_type": "sale",
            },
        )
        media = ServiceMedia.objects.get(title="Module night")
        self.assertEqual(media.deal, fresh)
        report = self.client.get(reverse("service-report"))
        self.assertContains(report, "По виду работ")
        self.assertContains(report, "Сервис модулей")
        fresh.refresh_from_db()
        self.assertEqual(fresh.revision, 2)

    def test_checks_warranty_route_merge_and_digest(self):
        from delayu.models_service import ServiceChecklist, ServiceCustomer, ServiceDeal, ServiceInvoice, ServiceTask

        page = self.client.get(reverse("service-playbooks"))
        self.assertContains(page, 'name="approval_amount" value="2500.00"')
        from delayu.models_service import ServicePlaybook

        sale_book = ServicePlaybook.objects.get(subsystem=self.sub, job_type="sale")
        saved = self.client.post(
            reverse("service-playbooks"),
            {
                "action": "norms",
                "book_id": sale_book.pk,
                "stale_days": "9",
                "warranty_days": "30",
                "approval_amount": "2 500,50",
                "after_hours": "After 18:00 we reply the next morning.",
            },
        )
        self.assertEqual(saved.status_code, 302)
        sale_book.refresh_from_db()
        self.assertEqual(sale_book.stale_days, 9)
        self.assertEqual(sale_book.approval_amount, Decimal("2500.50"))
        self.client.post(
            reverse("service-playbooks"),
            {"action": "deal", "customer": self.customer.pk, "job_type": "sale", "title": "Wall two"},
        )
        deal = ServiceDeal.objects.get(title="Wall two")
        deal.decision_maker = "yes"
        deal.screen_over_30 = "yes"
        deal.state = "AB"
        deal.event_on = "2026-11-02"
        deal.value = Decimal("1000.00")
        deal.save()
        blocked = self.client.post(
            reverse("service-customer", args=[self.customer.pk]),
            {"action": "advance", "deal_id": deal.pk, "stage": "qualified"},
        )
        self.assertEqual(blocked.status_code, 302)
        deal.refresh_from_db()
        self.assertEqual(deal.stage, "new_lead")
        for item in ServiceChecklist.objects.filter(playbook__subsystem=self.sub, playbook__job_type="sale"):
            self.client.post(
                reverse("service-customer", args=[self.customer.pk]),
                {"action": "check", "deal_id": deal.pk, "item_id": item.pk},
            )
        self.client.post(
            reverse("service-customer", args=[self.customer.pk]),
            {"action": "advance", "deal_id": deal.pk, "stage": "qualified"},
        )
        deal.refresh_from_db()
        self.assertEqual(deal.stage, "qualified")
        self.client.post(
            reverse("service-playbooks"),
            {"action": "route", "job_type": "sale", "province": "AB", "owner_name": "Liliya"},
        )
        self.client.post(
            reverse("service-customer", args=[self.customer.pk]),
            {"action": "route", "deal_id": deal.pk},
        )
        deal.refresh_from_db()
        self.assertEqual(deal.owner_name, "Liliya")
        self.client.post(
            reverse("service-customer", args=[self.customer.pk]),
            {"action": "note", "deal_id": deal.pk, "body": "не звонить до пятницы"},
        )
        self.client.post(
            reverse("service-customer", args=[self.customer.pk]),
            {"action": "next", "deal_id": deal.pk, "next_on": "2020-01-01"},
        )
        self.client.post(
            reverse("service-customer", args=[self.customer.pk]),
            {"action": "advance", "deal_id": deal.pk, "stage": "won"},
        )
        deal.refresh_from_db()
        self.assertEqual(deal.status, "won")
        self.assertIsNotNone(deal.warranty_on)
        self.assertTrue(ServiceTask.objects.filter(deal=deal, title="Закрыть дело с заказчиком").exists())
        card = self.client.get(reverse("service-customer", args=[self.customer.pk]))
        self.assertContains(card, "не звонить до пятницы")
        self.assertContains(card, "Редакция")
        queue = self.client.get(reverse("service-queue"))
        self.assertContains(queue, "каналов на паузе")
        report = self.client.get(reverse("service-report"))
        self.assertContains(report, "2026-11")
        self.assertContains(report, "Закрыто за 7 дней")
        self.assertContains(report, "Liliya")
        other = ServiceCustomer.objects.create(
            subsystem=self.sub,
            number="ZK-0099",
            display_name="Дубль",
            phone=self.customer.phone,
        )
        warned = self.client.get(reverse("service-customer", args=[self.customer.pk]))
        self.assertContains(warned, "Тот же телефон")
        self.client.post(
            reverse("service-customer", args=[self.customer.pk]),
            {"action": "merge", "other_id": other.pk},
        )
        self.assertFalse(ServiceCustomer.objects.filter(number="ZK-0099").exists())
        site = ServiceObject.objects.create(
            subsystem=self.sub, customer=self.customer, code="ST-9", title="Hall"
        )
        self.client.post(
            reverse("service-customer", args=[self.customer.pk]),
            {"action": "gear", "site_id": site.pk, "gear_title": "Cabinet", "serial": "SN-1"},
        )
        self.assertContains(
            self.client.get(reverse("service-customer", args=[self.customer.pk])),
            "SN-1",
        )
        self.client.post(
            reverse("service-invoices"),
            {"customer": self.customer.pk, "title": "Deposit wall", "amount": "10.00", "status": "draft"},
        )
        self.client.post(
            reverse("service-customer", args=[self.customer.pk]),
            {"action": "deposit"},
        )
        self.assertEqual(ServiceInvoice.objects.get(title="Deposit wall").kind, "deposit")
        sale = self.sub.service_playbooks.get(job_type="sale")
        self.client.post(
            reverse("service-playbooks"),
            {"action": "clone", "book_id": sale.pk, "code": "panels", "title": "Панели"},
        )
        self.assertTrue(self.sub.service_playbooks.filter(job_type="panels").exists())
        ServiceDeal.objects.filter(pk=deal.pk).update(
            updated_at=timezone.now() - timedelta(days=30), status="open", paused=False
        )
        from delayu.services.service_follow import stale_deals

        self.assertIn(deal.pk, [row.pk for row in stale_deals(self.sub)])
        stale = self.client.get(reverse("service-queue"))
        self.assertContains(stale, "без движения")
        self.assertContains(stale, "января 2020")

    def test_language_switch_translates_the_service_contour(self):
        russian = self.client.get(reverse("service-queue"))
        self.assertContains(russian, "Очередь дня")
        self.assertContains(russian, "RU")
        self.assertContains(russian, "EN")
        switched = self.client.post(
            reverse("set_language"),
            {"language": "en", "next": reverse("service-queue")},
        )
        self.assertEqual(switched.status_code, 302)
        english = self.client.get(reverse("service-queue"))
        self.assertContains(english, "Today's queue")
        self.assertContains(english, "Unassigned")
        self.assertContains(english, "A manager sees everything")
        self.assertContains(english, 'data-prefix="дело:"')
        self.assertContains(english, "обращение:номер, дело:ФИО")
        self.assertNotContains(english, "Очередь дня")
        playbooks = self.client.get(reverse("service-playbooks"))
        self.assertContains(playbooks, "One playbook per job type")
        self.assertContains(playbooks, "Playbooks")
        back = self.client.post(
            reverse("set_language"),
            {"language": "ru", "next": reverse("service-queue")},
        )
        self.assertEqual(back.status_code, 302)
        restored = self.client.get(reverse("service-queue"))
        self.assertContains(restored, "Очередь дня")
