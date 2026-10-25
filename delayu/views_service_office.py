"""Экраны календаря, сценариев, воронок, рассылок, рекламы, счетов и медиатеки."""
from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import TemplateView

from delayu.forms_service import CustomerForm
from delayu.forms_service_office import (
    AdForm,
    AdLeadForm,
    AppointmentForm,
    CalendarForm,
    FunnelForm,
    InvoiceForm,
    MailingForm,
    MediaForm,
    WorkflowForm,
)
from delayu.models_service import (
    ServiceAd,
    ServiceAppointment,
    ServiceCalendar,
    ServiceFunnel,
    ServiceInvoice,
    ServiceMailing,
    ServiceMedia,
    ServiceWorkflow,
)
from delayu.services.service_automation import ensure_workflows
from delayu.services.service_office import (
    apply_invoice_state,
    book_appointment,
    ensure_calendars,
    ensure_funnels,
    issue_invoice,
    next_custom_code,
    open_ad_lead,
    send_mailing,
    update_mailing,
)
from delayu.views_service import ServiceContourMixin, save_new_customer


class ServiceCalendarView(ServiceContourMixin, TemplateView):
    module_code = "S01"
    template_name = "platform/service/calendars.html"
    page_title = "Календари"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        subsystem = self.subsystem()
        calendars = list(ensure_calendars(subsystem))
        appointments = list(
            subsystem.service_appointments.select_related("calendar", "customer")[:30]
        )
        context["calendars"] = calendars
        context["calendar_rows"] = [
            {"item": calendar, "form": _calendar_form(calendar)} for calendar in calendars
        ]
        context["calendar_form"] = CalendarForm(
            prefix="newcal", initial={"minutes": 30, "kind": "meeting", "active": True}
        )
        context["appointments"] = appointments
        context["appointment_rows"] = [
            {"item": item, "form": _appointment_form(item)} for item in appointments
        ]
        context["form"] = AppointmentForm(subsystem=subsystem)
        context["customer_form"] = CustomerForm(initial={"stage": "new_lead", "payment_state": "none"})
        context["has_customers"] = subsystem.service_customers.exists()
        return context

    def post(self, request, *args, **kwargs):
        subsystem = self.subsystem()
        ensure_calendars(subsystem)
        form_action = request.POST.get("form_action") or "book"
        if form_action == "open_customer":
            customer = save_new_customer(request, subsystem)
            if customer is None:
                return self.get(request, *args, **kwargs)
            return redirect("service-calendars")
        if form_action == "create_calendar":
            form = CalendarForm(request.POST, prefix="newcal")
            if not form.is_valid():
                messages.error(request, "Календарь не создан: нужно название.")
                return self.get(request, *args, **kwargs)
            name = form.cleaned_data["name"].strip()
            if ServiceCalendar.objects.filter(subsystem=subsystem, name=name).exists():
                messages.error(request, "Календарь с таким названием уже есть.")
                return redirect("service-calendars")
            ServiceCalendar.objects.create(subsystem=subsystem, name=name, **{
                key: form.cleaned_data[key] for key in ("kind", "minutes", "owner_name", "active")
            })
            messages.success(request, f"Календарь «{name}» добавлен.")
            return redirect("service-calendars")
        if form_action == "save_calendar":
            calendar = get_object_or_404(
                ServiceCalendar, pk=request.POST.get("calendar_id"), subsystem=subsystem
            )
            form = CalendarForm(request.POST, prefix=f"c{calendar.pk}")
            if not form.is_valid():
                messages.error(request, "Календарь не сохранён.")
                return redirect("service-calendars")
            name = form.cleaned_data["name"].strip()
            taken = ServiceCalendar.objects.filter(subsystem=subsystem, name=name).exclude(pk=calendar.pk)
            if taken.exists():
                messages.error(request, "Календарь с таким названием уже есть.")
                return redirect("service-calendars")
            calendar.name = name
            calendar.kind = form.cleaned_data["kind"]
            calendar.minutes = form.cleaned_data["minutes"]
            calendar.owner_name = form.cleaned_data["owner_name"]
            calendar.active = form.cleaned_data["active"]
            calendar.save()
            messages.success(request, f"Календарь «{calendar.name}» сохранён.")
            return redirect("service-calendars")
        if form_action == "save_appointment":
            appointment = get_object_or_404(
                ServiceAppointment, pk=request.POST.get("appointment_id"), subsystem=subsystem
            )
            form = AppointmentForm(request.POST, subsystem=subsystem, prefix=f"a{appointment.pk}")
            if not form.is_valid():
                messages.error(request, "Встреча не сохранена: проверьте время.")
                return redirect("service-calendars")
            appointment.calendar = form.cleaned_data["calendar"]
            appointment.customer = form.cleaned_data["customer"]
            appointment.starts_at = form.cleaned_data["starts_at"]
            appointment.note = form.cleaned_data["note"]
            appointment.minutes = appointment.calendar.minutes
            appointment.save()
            messages.success(request, "Встреча сохранена.")
            return redirect("service-calendars")
        if form_action == "delete_appointment":
            ServiceAppointment.objects.filter(
                pk=request.POST.get("appointment_id"), subsystem=subsystem
            ).delete()
            messages.success(request, "Встреча снята.")
            return redirect("service-calendars")
        form = AppointmentForm(request.POST, subsystem=subsystem)
        if not form.is_valid():
            messages.error(request, "Встреча не записана: нужны календарь, заказчик и время.")
            return self.get(request, *args, **kwargs)
        appointment = book_appointment(
            calendar=form.cleaned_data["calendar"],
            customer=form.cleaned_data["customer"],
            starts_at=form.cleaned_data["starts_at"],
            note=form.cleaned_data["note"],
        )
        messages.success(request, f"Встреча в «{appointment.calendar.name}» записана.")
        return redirect("service-calendars")


class ServiceWorkflowView(ServiceContourMixin, TemplateView):
    module_code = "S01"
    template_name = "platform/service/workflows.html"
    page_title = "Сценарии"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        workflows = list(ensure_workflows(self.subsystem()))
        context["workflows"] = workflows
        context["workflow_rows"] = [
            {"item": item, "form": _workflow_form(item)} for item in workflows
        ]
        context["form"] = WorkflowForm()
        return context

    def post(self, request, *args, **kwargs):
        subsystem = self.subsystem()
        ensure_workflows(subsystem)
        if request.POST.get("form_action") == "save":
            workflow = get_object_or_404(
                ServiceWorkflow, pk=request.POST.get("workflow_id"), subsystem=subsystem
            )
            form = WorkflowForm(request.POST, prefix=f"w{workflow.pk}")
            if not form.is_valid():
                messages.error(request, "Сценарий не сохранён: нужно имя.")
                return redirect("service-workflows")
            workflow.name = form.cleaned_data["name"]
            workflow.folder = form.cleaned_data["folder"]
            workflow.trigger = form.cleaned_data["trigger"]
            workflow.action = form.cleaned_data["action"]
            workflow.save(update_fields=["name", "folder", "trigger", "action"])
            messages.success(request, f"Сценарий «{workflow.name}» сохранён.")
            return redirect("service-workflows")
        if request.POST.get("action") == "toggle":
            workflow = get_object_or_404(ServiceWorkflow, pk=request.POST.get("workflow_id"), subsystem=subsystem)
            workflow.status = (
                ServiceWorkflow.Status.DRAFT
                if workflow.status == ServiceWorkflow.Status.PUBLISHED
                else ServiceWorkflow.Status.PUBLISHED
            )
            workflow.save(update_fields=["status"])
            messages.success(request, f"«{workflow.name}»: {workflow.get_status_display()}.")
            return redirect("service-workflows")
        form = WorkflowForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Сценарий не создан: нужно имя.")
            return self.get(request, *args, **kwargs)
        workflow = ServiceWorkflow.objects.create(
            subsystem=subsystem,
            code=next_custom_code(subsystem),
            status=ServiceWorkflow.Status.PUBLISHED,
            **form.cleaned_data,
        )
        messages.success(request, f"Сценарий «{workflow.name}» опубликован.")
        return redirect("service-workflows")


class ServiceFunnelView(ServiceContourMixin, TemplateView):
    module_code = "S01"
    template_name = "platform/service/funnels.html"
    page_title = "Воронки сайта"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        funnels = list(ensure_funnels(self.subsystem()))
        context["funnels"] = funnels
        context["funnel_rows"] = [{"item": item, "form": _funnel_form(item)} for item in funnels]
        context["form"] = FunnelForm()
        return context

    def post(self, request, *args, **kwargs):
        subsystem = self.subsystem()
        if request.POST.get("form_action") == "save":
            funnel = get_object_or_404(ServiceFunnel, pk=request.POST.get("funnel_id"), subsystem=subsystem)
            form = FunnelForm(request.POST, prefix=f"fn{funnel.pk}")
            if not form.is_valid():
                messages.error(request, "Воронка не сохранена: нужны название и шаги.")
                return redirect("service-funnels")
            name = form.cleaned_data["name"].strip()
            taken = ServiceFunnel.objects.filter(subsystem=subsystem, name=name).exclude(pk=funnel.pk)
            if taken.exists():
                messages.error(request, "Воронка с таким названием уже есть.")
                return redirect("service-funnels")
            funnel.name = name
            funnel.steps = form.cleaned_data["steps"]
            funnel.status = form.cleaned_data["status"]
            funnel.save()
            messages.success(request, f"Воронка «{funnel.name}» сохранена.")
            return redirect("service-funnels")
        if request.POST.get("action") == "toggle":
            funnel = get_object_or_404(ServiceFunnel, pk=request.POST.get("funnel_id"), subsystem=subsystem)
            funnel.status = (
                ServiceFunnel.Status.DRAFT
                if funnel.status == ServiceFunnel.Status.ACTIVE
                else ServiceFunnel.Status.ACTIVE
            )
            funnel.save(update_fields=["status"])
            messages.success(request, f"«{funnel.name}»: {funnel.get_status_display()}.")
            return redirect("service-funnels")
        form = FunnelForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Воронка не создана: нужны название и шаги.")
            return self.get(request, *args, **kwargs)
        funnel, created = ServiceFunnel.objects.get_or_create(
            subsystem=subsystem,
            name=form.cleaned_data["name"],
            defaults={"steps": form.cleaned_data["steps"], "status": form.cleaned_data["status"]},
        )
        if not created:
            funnel.steps = form.cleaned_data["steps"]
            funnel.status = form.cleaned_data["status"]
            funnel.save(update_fields=["steps", "status"])
        messages.success(request, f"Воронка «{funnel.name}» сохранена.")
        return redirect("service-funnels")


class ServiceMailingView(ServiceContourMixin, TemplateView):
    module_code = "S01"
    template_name = "platform/service/mailings.html"
    page_title = "Рассылки"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        mailings = list(self.subsystem().service_mailings.all())
        context["mailings"] = mailings
        context["mailing_rows"] = [{"item": item, "form": _mailing_form(item)} for item in mailings]
        context["form"] = MailingForm()
        return context

    def post(self, request, *args, **kwargs):
        form_action = request.POST.get("form_action") or ""
        if form_action in {"save", "resend"}:
            mailing = get_object_or_404(
                ServiceMailing, pk=request.POST.get("mailing_id"), subsystem=self.subsystem()
            )
            form = MailingForm(request.POST, prefix=f"ml{mailing.pk}")
            if not form.is_valid():
                messages.error(request, "Рассылка не сохранена: нужны тема и текст.")
                return redirect("service-mailings")
            update_mailing(mailing, resend=form_action == "resend", **form.cleaned_data)
            note = "и снова записана в карточки" if form_action == "resend" else "сохранена"
            messages.success(request, f"«{mailing.subject}» {note}.")
            return redirect("service-mailings")
        form = MailingForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Рассылка не ушла: нужны тема и текст.")
            return self.get(request, *args, **kwargs)
        mailing = send_mailing(subsystem=self.subsystem(), **form.cleaned_data)
        messages.success(request, f"Письмо «{mailing.subject}» записано в {mailing.sent_count} карточек.")
        return redirect("service-mailings")


class ServiceAdView(ServiceContourMixin, TemplateView):
    module_code = "S01"
    template_name = "platform/service/ads.html"
    page_title = "Реклама"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        subsystem = self.subsystem()
        from delayu.services.service_snapshot import load_ads

        load_ads(subsystem)
        ads = list(ServiceAd.objects.filter(subsystem=subsystem))
        context["ads"] = ads
        context["ad_rows"] = [{"item": ad, "form": _ad_form(ad)} for ad in ads]
        context["form"] = AdForm()
        context["lead_form"] = AdLeadForm(subsystem=subsystem)
        return context

    def post(self, request, *args, **kwargs):
        subsystem = self.subsystem()
        form_action = request.POST.get("form_action") or ""
        if form_action == "save":
            ad = get_object_or_404(ServiceAd, pk=request.POST.get("ad_id"), subsystem=subsystem)
            form = AdForm(request.POST, prefix=f"ad{ad.pk}")
            if not form.is_valid():
                messages.error(request, "Кампания не сохранена.")
                return redirect("service-ads")
            for field, value in form.cleaned_data.items():
                setattr(ad, field, value)
            ad.save()
            messages.success(request, f"Кампания «{ad.name}» сохранена.")
            return redirect("service-ads")
        if form_action == "toggle":
            ad = get_object_or_404(ServiceAd, pk=request.POST.get("ad_id"), subsystem=subsystem)
            ad.active = not ad.active
            ad.save(update_fields=["active"])
            messages.success(request, f"«{ad.name}»: {'включена' if ad.active else 'выключена'}.")
            return redirect("service-ads")
        if request.POST.get("action") == "lead":
            form = AdLeadForm(request.POST, subsystem=subsystem)
            if not form.is_valid():
                messages.error(request, "Лид не открыт: выберите кампанию и имя.")
                return self.get(request, *args, **kwargs)
            customer, deal = open_ad_lead(
                ad=form.cleaned_data["ad"],
                display_name=form.cleaned_data["display_name"],
                phone=form.cleaned_data["phone"],
            )
            messages.success(request, f"Лид {deal.number} из «{form.cleaned_data['ad'].name}».")
            return redirect("service-customer", pk=customer.pk)
        form = AdForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Кампания не создана.")
            return self.get(request, *args, **kwargs)
        ad = ServiceAd.objects.create(subsystem=subsystem, **form.cleaned_data)
        messages.success(request, f"Кампания «{ad.name}» включена.")
        return redirect("service-ads")


class ServiceInvoiceView(ServiceContourMixin, TemplateView):
    module_code = "S01"
    template_name = "platform/service/invoices.html"
    page_title = "Счета"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        subsystem = self.subsystem()
        invoices = list(subsystem.service_invoices.select_related("customer"))
        context["invoices"] = invoices
        context["invoice_rows"] = [
            {"item": item, "form": _invoice_form(item)} for item in invoices
        ]
        context["form"] = InvoiceForm(subsystem=subsystem)
        context["customer_form"] = CustomerForm(initial={"stage": "new_lead", "payment_state": "none"})
        context["has_customers"] = subsystem.service_customers.exists()
        return context

    def post(self, request, *args, **kwargs):
        subsystem = self.subsystem()
        if request.POST.get("action") == "open_customer":
            customer = save_new_customer(request, subsystem)
            if customer is None:
                return self.get(request, *args, **kwargs)
            return redirect("service-invoices")
        if request.POST.get("form_action") == "save":
            invoice = get_object_or_404(
                ServiceInvoice, pk=request.POST.get("invoice_id"), subsystem=subsystem
            )
            form = InvoiceForm(request.POST, subsystem=subsystem, prefix=f"i{invoice.pk}")
            if not form.is_valid():
                messages.error(request, "Счёт не сохранён: проверьте заказчика и сумму.")
                return redirect("service-invoices")
            invoice.customer = form.cleaned_data["customer"]
            invoice.title = form.cleaned_data["title"]
            invoice.amount = form.cleaned_data["amount"]
            invoice.status = form.cleaned_data["status"]
            invoice.save()
            apply_invoice_state(invoice)
            messages.success(request, f"{invoice.number}: {invoice.get_status_display()}.")
            return redirect("service-invoices")
        form = InvoiceForm(request.POST, subsystem=subsystem)
        if not form.is_valid():
            messages.error(request, "Счёт не создан: нужны заказчик, название и сумма.")
            return self.get(request, *args, **kwargs)
        invoice = issue_invoice(**form.cleaned_data)
        messages.success(request, f"{invoice.number}: {invoice.get_status_display()}.")
        return redirect("service-invoices")


class ServiceMediaView(ServiceContourMixin, TemplateView):
    module_code = "S01"
    template_name = "platform/service/media.html"
    page_title = "Медиатека"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items = list(self.subsystem().service_media.all())
        context["items"] = items
        context["media_rows"] = [{"item": item, "form": _media_form(item)} for item in items]
        context["form"] = MediaForm(subsystem=self.subsystem())
        return context

    def post(self, request, *args, **kwargs):
        subsystem = self.subsystem()
        form_action = request.POST.get("form_action") or ""
        if form_action == "delete":
            item = get_object_or_404(ServiceMedia, pk=request.POST.get("media_id"), subsystem=subsystem)
            title = item.title
            item.delete()
            messages.success(request, f"«{title}» убрано из медиатеки.")
            return redirect("service-media")
        if form_action == "save":
            item = get_object_or_404(ServiceMedia, pk=request.POST.get("media_id"), subsystem=subsystem)
            form = MediaForm(request.POST, request.FILES, subsystem=subsystem, prefix=f"m{item.pk}")
            if not form.is_valid():
                messages.error(request, "Карточка файла не сохранена.")
                return redirect("service-media")
            data = dict(form.cleaned_data)
            upload = data.pop("file")
            for field, value in data.items():
                setattr(item, field, value)
            if upload:
                item.file = upload
            item.save()
            messages.success(request, f"«{item.title}» сохранено.")
            return redirect("service-media")
        form = MediaForm(request.POST, request.FILES, subsystem=subsystem)
        if not form.is_valid():
            messages.error(request, "Файл не добавлен: нужно название.")
            return self.get(request, *args, **kwargs)
        data = dict(form.cleaned_data)
        upload = data.pop("file")
        item = ServiceMedia(subsystem=self.subsystem(), **data)
        if upload:
            item.file = upload
        item.save()
        messages.success(request, f"«{item.title}» в медиатеке.")
        return redirect("service-media")


def _calendar_form(calendar: ServiceCalendar) -> CalendarForm:
    return CalendarForm(
        prefix=f"c{calendar.pk}",
        initial={
            "name": calendar.name,
            "kind": calendar.kind,
            "minutes": calendar.minutes,
            "owner_name": calendar.owner_name,
            "active": calendar.active,
        },
    )


def _appointment_form(item: ServiceAppointment) -> AppointmentForm:
    return AppointmentForm(
        subsystem=item.subsystem,
        prefix=f"a{item.pk}",
        initial={
            "calendar": item.calendar_id,
            "customer": item.customer_id,
            "starts_at": item.starts_at,
            "note": item.note,
        },
    )


def _workflow_form(item: ServiceWorkflow) -> WorkflowForm:
    return WorkflowForm(
        prefix=f"w{item.pk}",
        initial={
            "name": item.name,
            "folder": item.folder,
            "trigger": item.trigger,
            "action": item.action,
        },
    )


def _funnel_form(item: ServiceFunnel) -> FunnelForm:
    return FunnelForm(
        prefix=f"fn{item.pk}",
        initial={"name": item.name, "steps": item.steps, "status": item.status},
    )


def _mailing_form(item: ServiceMailing) -> MailingForm:
    return MailingForm(
        prefix=f"ml{item.pk}",
        initial={"subject": item.subject, "audience": item.audience, "body": item.body},
    )


def _ad_form(ad: ServiceAd) -> AdForm:
    return AdForm(
        prefix=f"ad{ad.pk}",
        initial={
            "name": ad.name,
            "network": ad.network,
            "province": ad.province,
            "job_type": ad.job_type,
        },
    )


def _invoice_form(item: ServiceInvoice) -> InvoiceForm:
    return InvoiceForm(
        subsystem=item.subsystem,
        prefix=f"i{item.pk}",
        initial={
            "customer": item.customer_id,
            "title": item.title,
            "amount": item.amount,
            "status": item.status,
        },
    )


def _media_form(item: ServiceMedia) -> MediaForm:
    return MediaForm(
        subsystem=item.subsystem,
        prefix=f"m{item.pk}",
        initial={
            "folder": item.folder,
            "title": item.title,
            "kind": item.kind,
            "note": item.note,
            "deal": item.deal_id,
            "job_type": item.job_type,
        },
    )
