"""Экраны сервисного контура: карточка заказчика и объекты."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.generic import TemplateView

from delayu.forms_service import (
    ChannelForm,
    CustomerForm,
    TaskForm,
    DealForm,
    DeploymentForm,
    ObjectForm,
    RentalQuoteForm,
    SaleQuoteForm,
    VisitForm,
)
from delayu.mixins import ModulePermissionMixin
from delayu.models_service import (
    ServiceChannel,
    ServiceCustomer,
    ServiceDeal,
    ServiceDeployment,
    ServiceMessage,
    ServiceObject,
    ServiceTask,
    ServiceVisit,
)
from delayu.services.access import get_membership_or_403
from delayu.services.service_agent import ask_and_record, queue_notice
from delayu.services.service_channels import CHANNEL_CODES, ensure_channels
from delayu.services.service_deals import create_deal, ensure_deal, move_deal, push_customer_stage
from delayu.services.service_inbound import LIVE_CHANNELS, receive_inbound
from delayu.services.service_intake import open_quote
from delayu.services.service_dialogue import ServiceFlowError, post_message, release_due
from delayu.services.service_process import (
    add_contact,
    add_crew,
    advance_deal,
    assign_owner,
    customer_process,
    link_site,
    pause_deal,
    post_playbook_message,
    repeat_deal,
    resume_deal,
    universal_stage,
)
from delayu.services.service_follow import (
    add_gear,
    add_note,
    apply_route,
    mark_deposit,
    merge_customers,
    set_next,
    toggle_check,
)
from delayu.services.service_field import customer_totals, object_totals

_JOB_FIELDS = (
    "title",
    "address",
    "city",
    "state",
    "job_type",
    "placement",
    "width_ft",
    "height_ft",
    "event_on",
    "stage",
    "status",
    "notes",
)


def _parse_when(raw: str):
    text = (raw or "").strip()
    if not text:
        return None
    moment = parse_datetime(text)
    if moment is None and len(text) == 16:
        moment = parse_datetime(text + ":00")
    if moment is None:
        return None
    if timezone.is_naive(moment):
        moment = timezone.make_aware(moment, timezone.get_current_timezone())
    return moment


def _next_number(model, subsystem, prefix: str) -> str:
    last = (
        model.objects.filter(subsystem=subsystem, number__startswith=prefix)
        if hasattr(model, "number")
        else model.objects.filter(subsystem=subsystem, code__startswith=prefix)
    )
    field = "number" if hasattr(model, "number") else "code"
    seq = 0
    for value in last.values_list(field, flat=True):
        tail = str(value).rsplit("-", 1)[-1]
        if tail.isdigit():
            seq = max(seq, int(tail))
    return f"{prefix}{seq + 1:04d}"


class ServiceContourMixin(ModulePermissionMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        membership = get_membership_or_403(request)
        if membership.subsystem.industry_template != "service":
            raise PermissionDenied("Раздел доступен только в сервисном контуре")
        self.service_membership = membership
        return super().dispatch(request, *args, **kwargs)

    def subsystem(self):
        return self.service_membership.subsystem


class ServiceHubView(ServiceContourMixin, TemplateView):
    module_code = "S01"
    template_name = "platform/service/hub.html"
    page_title = "Сервисный контур"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        subsystem = self.subsystem()
        ensure_channels(subsystem)
        from delayu.services.service_snapshot import load_canadian_led

        load_canadian_led(subsystem)
        customers = ServiceCustomer.objects.filter(subsystem=subsystem)
        context.update(
            {
                "customer_count": customers.count(),
                "deal_count": ServiceDeal.objects.filter(subsystem=subsystem).count(),
                "object_count": ServiceObject.objects.filter(subsystem=subsystem).count(),
                "due_count": ServiceMessage.objects.filter(
                    subsystem=subsystem,
                    status=ServiceMessage.Status.SCHEDULED,
                    scheduled_for__lte=timezone.now(),
                ).count(),
                "waiting_count": ServiceMessage.objects.filter(
                    subsystem=subsystem, status=ServiceMessage.Status.SCHEDULED
                ).count(),
                "recent": customers[:8],
                "workflow_count": subsystem.service_workflows.count(),
                "field_count": subsystem.service_fields.count(),
                "form_count": subsystem.service_forms.count(),
                "phone_count": subsystem.service_phones.count(),
            }
        )
        return context


class ServiceCustomerListView(ServiceContourMixin, TemplateView):
    module_code = "S01"
    template_name = "platform/service/customers.html"
    page_title = "Заказчики"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["customers"] = ServiceCustomer.objects.filter(subsystem=self.subsystem())
        context["form"] = CustomerForm(initial={"stage": "new_lead", "payment_state": "none"})
        return context

    def post(self, request, *args, **kwargs):
        customer = save_new_customer(request, self.subsystem())
        if customer is None:
            return self.get(request, *args, **kwargs)
        return redirect("service-customer", pk=customer.pk)


class ServiceDealBoardView(ServiceContourMixin, TemplateView):
    module_code = "S01"
    template_name = "platform/service/deals.html"
    page_title = "Воронка LED SALES"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        subsystem = self.subsystem()
        deals = list(
            ServiceDeal.objects.filter(subsystem=subsystem).select_related("customer")
        )
        def pack(selected):
            return [{"deal": deal, "form": _deal_form(deal)} for deal in selected]

        columns = []
        for code, label in ServiceCustomer.Stage.choices:
            columns.append(
                {
                    "code": code,
                    "label": label,
                    "deals": pack(
                        deal
                        for deal in deals
                        if deal.status != ServiceDeal.Status.LOST and deal.stage == code
                    ),
                }
            )
        columns.append(
            {
                "code": "lost",
                "label": "Lost",
                "deals": pack(deal for deal in deals if deal.status == ServiceDeal.Status.LOST),
            }
        )
        context["columns"] = columns
        context["stages"] = list(ServiceCustomer.Stage.choices) + [("lost", "Lost")]
        context["form"] = DealForm(
            subsystem=subsystem,
            initial={
                "stage": ServiceCustomer.Stage.NEW_LEAD,
                "job_type": ServiceCustomer.JobType.SALE,
                "placement": ServiceCustomer.Placement.INDOOR,
                "decision_maker": ServiceDeal.Answer.UNKNOWN,
                "screen_over_30": ServiceDeal.Answer.UNKNOWN,
                "guests_over_200": ServiceDeal.Answer.UNKNOWN,
                "church_project": ServiceDeal.Answer.UNKNOWN,
            },
        )
        context["has_customers"] = ServiceCustomer.objects.filter(subsystem=subsystem).exists()
        context["customer_form"] = CustomerForm(initial={"stage": "new_lead", "payment_state": "none"})
        return context

    def post(self, request, *args, **kwargs):
        subsystem = self.subsystem()
        action = request.POST.get("action") or "create"
        if action == "open_customer":
            customer = save_new_customer(request, subsystem)
            if customer is None:
                return self.get(request, *args, **kwargs)
            return redirect("service-deals")
        if action == "edit":
            deal = get_object_or_404(ServiceDeal, pk=request.POST.get("deal_id"), subsystem=subsystem)
            form = DealForm(request.POST, subsystem=subsystem, lock_customer=True, prefix=f"d{deal.pk}")
            if not form.is_valid():
                messages.error(request, "Сделка не сохранена: проверьте название и стадию.")
            else:
                form.apply(deal)
                messages.success(request, f"{deal.number} сохранена. {deal.qualification}")
            return redirect("service-deals")
        if action == "move":
            deal = get_object_or_404(ServiceDeal, pk=request.POST.get("deal_id"), subsystem=subsystem)
            stage = request.POST.get("stage") or deal.stage
            allowed = {code for code, _label in ServiceCustomer.Stage.choices} | {"lost"}
            if stage not in allowed:
                messages.error(request, "Такой стадии в воронке нет.")
            else:
                move_deal(deal, stage)
                messages.success(request, f"{deal.number}: {deal.get_stage_display() if stage != 'lost' else 'Lost'}.")
            return redirect("service-deals")
        form = DealForm(request.POST, subsystem=subsystem)
        if not form.is_valid():
            messages.error(request, "Сделка не открыта: проверьте заказчика и название.")
            return self.get(request, *args, **kwargs)
        customer = form.cleaned_data["customer"]
        deal = create_deal(
            customer=customer,
            title=form.cleaned_data["title"],
            stage=form.cleaned_data["stage"],
        )
        form.apply(deal)
        messages.success(
            request,
            f"Сделка {deal.number} стоит в {deal.get_stage_display()}. {deal.qualification}",
        )
        return redirect("service-deals")


class ServiceQuoteView(ServiceContourMixin, TemplateView):
    module_code = "S01"
    template_name = "platform/service/quotes.html"
    page_title = "Заявки с сайта"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        unknown = {
            "decision_maker": ServiceDeal.Answer.UNKNOWN,
            "screen_over_30": ServiceDeal.Answer.UNKNOWN,
            "church_project": ServiceDeal.Answer.UNKNOWN,
            "guests_over_200": ServiceDeal.Answer.UNKNOWN,
        }
        context["sale_form"] = SaleQuoteForm(initial=unknown)
        context["rental_form"] = RentalQuoteForm(initial=unknown)
        context["recent"] = ServiceDeal.objects.filter(
            subsystem=self.subsystem(), source__startswith="Website"
        ).select_related("customer")[:12]
        return context

    def post(self, request, *args, **kwargs):
        kind = request.POST.get("kind") or "sale"
        form = SaleQuoteForm(request.POST) if kind == "sale" else RentalQuoteForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Заявка не открыта: нужно имя.")
            return self.get(request, *args, **kwargs)
        data = dict(form.cleaned_data)
        catalog = bool(data.pop("send_catalog", False))
        customer, deal = open_quote(
            subsystem=self.subsystem(), kind=kind, data=data, catalog=catalog
        )
        messages.success(
            request,
            f"Заявка {customer.number} открыла сделку {deal.number} в {deal.get_stage_display()}.",
        )
        return redirect("service-customer", pk=customer.pk)


class ServiceCustomerDetailView(ServiceContourMixin, TemplateView):
    module_code = "S01"
    template_name = "platform/service/customer.html"
    page_title = "Карточка заказчика"

    def _customer(self):
        return get_object_or_404(
            ServiceCustomer, pk=self.kwargs["pk"], subsystem=self.subsystem()
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer = self._customer()
        ensure_channels(customer.subsystem)
        channels = ServiceChannel.objects.filter(subsystem=customer.subsystem)
        context.update(
            {
                "customer": customer,
                "form": CustomerForm(initial=_customer_initial(customer)),
                "channels": channels,
                "ready_channels": channels.filter(status=ServiceChannel.Status.READY),
                "thread": customer.messages.select_related("created_by"),
                "sites": customer.sites.all(),
                "deals": [
                    {
                        "deal": deal,
                        "form": _deal_form(deal),
                        "universal": universal_stage("lost" if deal.status == "lost" else deal.stage),
                    }
                    for deal in customer.deals.all()
                ],
                "stages": ServiceCustomer.Stage.choices,
                "totals": customer_totals(customer),
                "tasks": customer.tasks.all(),
                "task_form": TaskForm(),
                **customer_process(customer),
            }
        )
        context["page_title"] = customer.display_name
        return context

    def post(self, request, *args, **kwargs):
        customer = self._customer()
        action = request.POST.get("action") or "save"
        try:
            if action == "save":
                form = CustomerForm(request.POST)
                if not form.is_valid():
                    messages.error(request, "Карточка не сохранена: проверьте поля.")
                else:
                    form.apply(customer)
                    push_customer_stage(customer)
                    messages.success(request, "Атрибуты карточки сохранены.")
            elif action == "inbound":
                post_message(
                    customer=customer,
                    channel=request.POST.get("channel") or "sms",
                    direction=ServiceMessage.Direction.IN,
                    author_kind=ServiceMessage.AuthorKind.CUSTOMER,
                    body=request.POST.get("body") or "",
                    user=request.user,
                )
                messages.success(request, "Входящее записано в карточку.")
            elif action == "ask":
                ask_and_record(
                    customer=customer,
                    channel=request.POST.get("channel") or "sms",
                    question=request.POST.get("body") or "",
                    user=request.user,
                )
                messages.success(request, "Агент ответил в той же карточке.")
            elif action in {"stage", "payment"}:
                queue_notice(
                    customer=customer,
                    channel=request.POST.get("channel") or "sms",
                    kind=action,
                    scheduled_for=_parse_when(request.POST.get("when") or ""),
                    user=request.user,
                )
                messages.success(request, "Сообщение агента поставлено в карточку.")
            elif action == "edit_deal":
                deal = get_object_or_404(
                    ServiceDeal, pk=request.POST.get("deal_id"), customer=customer
                )
                form = DealForm(
                    request.POST, subsystem=customer.subsystem, lock_customer=True, prefix=f"d{deal.pk}"
                )
                if not form.is_valid():
                    messages.error(request, "Сделка не сохранена: проверьте название и стадию.")
                else:
                    form.apply(deal)
                    messages.success(request, f"{deal.number} сохранена. {deal.qualification}")
            elif action == "move_deal":
                deal = get_object_or_404(
                    ServiceDeal, pk=request.POST.get("deal_id"), customer=customer
                )
                move_deal(deal, request.POST.get("stage") or deal.stage)
                messages.success(request, f"{deal.number} перенесена: {deal.get_stage_display()}.")
            elif action == "task":
                form = TaskForm(request.POST)
                if not form.is_valid():
                    messages.error(request, "Задача не поставлена: нужно название.")
                else:
                    data = dict(form.cleaned_data)
                    data["kind"] = data.get("kind") or ServiceTask.Kind.CALL
                    ServiceTask.objects.create(
                        subsystem=customer.subsystem,
                        customer=customer,
                        deal=customer.deals.exclude(status="lost").order_by("-updated_at").first(),
                        **data,
                    )
                    messages.success(request, "Задача поставлена на карточку.")
            elif action in {"advance", "repeat", "pause", "resume", "owner", "playbook_message", "site_link", "crew"}:
                deal = get_object_or_404(
                    ServiceDeal, pk=request.POST.get("deal_id"), customer=customer
                )
                actor = request.user.get_username()
                if action == "advance":
                    if request.POST.get("stage") == "lost":
                        deal.lost_reason = (request.POST.get("lost_reason") or "").strip()
                        deal.save(update_fields=["lost_reason", "updated_at"])
                    advance_deal(deal, request.POST.get("stage") or deal.stage, actor=actor)
                    messages.success(request, f"{deal.number}: плейбук пропустил стадию.")
                elif action == "repeat":
                    fresh = repeat_deal(deal, actor=actor)
                    messages.success(request, f"{fresh.number} открыто на той же карточке.")
                elif action == "pause":
                    pause_deal(deal, request.POST.get("pause_reason") or "", actor=actor)
                    messages.success(request, f"{deal.number} на паузе. Канал при этом не глушится.")
                elif action == "resume":
                    resume_deal(deal, actor=actor)
                    messages.success(request, f"{deal.number}: пауза снята, SLA снова идёт.")
                elif action == "owner":
                    assign_owner(
                        deal,
                        request.POST.get("owner_name") or "",
                        request.POST.get("observers") or "",
                        actor=actor,
                    )
                    messages.success(request, f"{deal.number}: владелец записан.")
                elif action == "playbook_message":
                    post_playbook_message(deal, user=request.user)
                    messages.success(request, "Текст плейбука записан в карточку по-английски.")
                elif action == "site_link":
                    site = get_object_or_404(
                        ServiceObject, pk=request.POST.get("site_id"), customer=customer
                    )
                    link_site(deal, site)
                    messages.success(request, f"{site.code} привязана к {deal.number}.")
                else:
                    site = None
                    if request.POST.get("site_id"):
                        site = get_object_or_404(
                            ServiceObject, pk=request.POST.get("site_id"), customer=customer
                        )
                    add_crew(
                        deal,
                        title=request.POST.get("crew_title") or "",
                        kind=request.POST.get("crew_kind") or "people",
                        planned=request.POST.get("planned") or 0,
                        actual=request.POST.get("actual") or 0,
                        unit=request.POST.get("unit") or "чел",
                        site=site,
                        damaged=request.POST.get("damaged") == "on",
                    )
                    messages.success(request, "План и факт сил записаны на дело.")
            elif action == "contact":
                add_contact(
                    customer,
                    name=request.POST.get("name") or "",
                    role_name=request.POST.get("role_name") or "",
                    phone=request.POST.get("phone") or "",
                    email=request.POST.get("email") or "",
                    decides=request.POST.get("decides") == "on",
                )
                messages.success(request, "Контакт добавлен на карточку.")
            elif action == "check":
                from delayu.models_service import ServiceChecklist

                deal = get_object_or_404(ServiceDeal, pk=request.POST.get("deal_id"), customer=customer)
                item = get_object_or_404(ServiceChecklist, pk=request.POST.get("item_id"))
                toggle_check(deal, item)
                messages.success(request, "Пункт плейбука обновлён.")
            elif action == "next":
                deal = get_object_or_404(ServiceDeal, pk=request.POST.get("deal_id"), customer=customer)
                raw = (request.POST.get("next_on") or "").strip()
                day = None
                if raw:
                    from datetime import date

                    try:
                        day = date.fromisoformat(raw)
                    except ValueError as exc:
                        raise ServiceFlowError("Дата следующего действия записывается как ГГГГ-ММ-ДД.") from exc
                set_next(deal, day, actor=request.user.get_username())
                messages.success(request, "Следующее действие записано.")
            elif action == "note":
                deal = get_object_or_404(ServiceDeal, pk=request.POST.get("deal_id"), customer=customer)
                add_note(deal, request.POST.get("body") or "", actor=request.user.get_username())
                messages.success(request, "Заметка видна сотрудникам и не уходит заказчику.")
            elif action == "route":
                deal = get_object_or_404(ServiceDeal, pk=request.POST.get("deal_id"), customer=customer)
                apply_route(deal, actor=request.user.get_username())
                messages.success(request, f"{deal.number}: владелец взят из маршрута провинции.")
            elif action == "gear":
                site = get_object_or_404(ServiceObject, pk=request.POST.get("site_id"), customer=customer)
                add_gear(site, request.POST.get("gear_title") or "", request.POST.get("serial") or "")
                messages.success(request, "Серийный номер записан на площадку.")
            elif action == "merge":
                other = get_object_or_404(
                    ServiceCustomer, pk=request.POST.get("other_id"), subsystem=customer.subsystem
                )
                merge_customers(customer, other, actor=request.user.get_username())
                messages.success(request, f"{other.number} собрана в {customer.number}.")
            elif action == "deposit":
                invoice = customer.invoices.order_by("-pk").first()
                if invoice is None:
                    raise ServiceFlowError("Счёта на карточке ещё нет.")
                mark_deposit(invoice)
                messages.success(request, f"{invoice.number}: {invoice.kind}.")
            elif action == "task_toggle":
                task = get_object_or_404(ServiceTask, pk=request.POST.get("task_id"), customer=customer)
                task.done = not task.done
                task.save(update_fields=["done"])
                messages.success(request, "Задача обновлена.")
            elif action == "release":
                count = release_due(customer.subsystem)
                messages.success(request, f"В карточки ушло сообщений: {count}.")
        except ServiceFlowError as exc:
            messages.error(request, str(exc))
        return redirect("service-customer", pk=customer.pk)


class ServiceChannelListView(ServiceContourMixin, TemplateView):
    module_code = "S01"
    template_name = "platform/service/channels.html"
    page_title = "Каналы"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        channels = list(ensure_channels(self.subsystem()))
        context["channels"] = channels
        context["live_channels"] = [channel for channel in channels if channel.code in LIVE_CHANNELS]
        context["channel_rows"] = [
            {
                "item": channel,
                "seeded": channel.code in CHANNEL_CODES,
                "form": ChannelForm(
                    prefix=f"ch{channel.pk}",
                    initial={"title": channel.title, "detail": channel.detail},
                ),
            }
            for channel in channels
        ]
        context["channel_form"] = ChannelForm(prefix="newch", include_code=True)
        return context

    def post(self, request, *args, **kwargs):
        subsystem = self.subsystem()
        form_action = request.POST.get("form_action") or ""
        if request.POST.get("action") == "inbound":
            try:
                customer, _message, created = receive_inbound(
                    subsystem=self.subsystem(),
                    channel=request.POST.get("channel") or "sms",
                    address=request.POST.get("address") or "",
                    body=request.POST.get("body") or "",
                    user=request.user,
                )
            except ServiceFlowError as exc:
                messages.error(request, str(exc))
                return redirect("service-channels")
            note = "Открыта новая сделка New Lead." if created else "Записано в существующую карточку."
            messages.success(request, f"{customer.number}: {note}")
            return redirect("service-customer", pk=customer.pk)
        if form_action == "save":
            channel = get_object_or_404(
                ServiceChannel, pk=request.POST.get("channel_id"), subsystem=subsystem
            )
            form = ChannelForm(request.POST, prefix=f"ch{channel.pk}")
            if not form.is_valid():
                messages.error(request, "Канал не сохранён: проверьте название.")
            else:
                channel.title = form.cleaned_data["title"]
                channel.detail = form.cleaned_data["detail"]
                channel.save(update_fields=["title", "detail"])
                messages.success(request, f"«{channel.title}» сохранён.")
            return redirect("service-channels")
        if form_action == "create":
            form = ChannelForm(request.POST, prefix="newch", include_code=True)
            if not form.is_valid():
                messages.error(request, "Канал не добавлен: нужны название, описание и код.")
                return self.get(request, *args, **kwargs)
            code = form.cleaned_data["code"]
            if ServiceChannel.objects.filter(subsystem=subsystem, code=code).exists():
                messages.error(request, "Канал с таким кодом уже есть.")
                return redirect("service-channels")
            ServiceChannel.objects.create(
                subsystem=subsystem,
                code=code,
                title=form.cleaned_data["title"],
                detail=form.cleaned_data["detail"],
            )
            messages.success(request, f"Канал «{form.cleaned_data['title']}» добавлен.")
            return redirect("service-channels")
        if form_action == "delete":
            channel = get_object_or_404(
                ServiceChannel, pk=request.POST.get("channel_id"), subsystem=subsystem
            )
            if channel.code in CHANNEL_CODES:
                messages.error(request, "Этот канал входит в набор контура. Его можно поставить на паузу.")
            else:
                title = channel.title
                channel.delete()
                messages.success(request, f"Канал «{title}» удалён.")
            return redirect("service-channels")
        channel = get_object_or_404(
            ServiceChannel, pk=request.POST.get("channel_id"), subsystem=self.subsystem()
        )
        channel.status = (
            ServiceChannel.Status.PAUSED
            if channel.status == ServiceChannel.Status.READY
            else ServiceChannel.Status.READY
        )
        channel.save(update_fields=["status"])
        messages.success(request, f"«{channel.title}»: {channel.get_status_display()}.")
        return redirect("service-channels")


class ServiceObjectListView(ServiceContourMixin, TemplateView):
    module_code = "S02"
    template_name = "platform/service/objects.html"
    page_title = "Объекты"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        subsystem = self.subsystem()
        sites = ServiceObject.objects.filter(subsystem=subsystem).select_related("customer")
        context["sites"] = [(site, object_totals(site)) for site in sites]
        context["form"] = ObjectForm(
            subsystem=subsystem,
            initial={"stage": "proposal", "status": "planned", "job_type": "rental", "placement": "indoor"},
        )
        context["has_customers"] = ServiceCustomer.objects.filter(subsystem=subsystem).exists()
        context["customer_form"] = CustomerForm(initial={"stage": "new_lead", "payment_state": "none"})
        return context

    def post(self, request, *args, **kwargs):
        subsystem = self.subsystem()
        if request.POST.get("action") == "open_customer":
            customer = save_new_customer(request, subsystem)
            if customer is None:
                return self.get(request, *args, **kwargs)
            return redirect("service-objects")
        form = ObjectForm(request.POST, subsystem=subsystem)
        if not form.is_valid():
            messages.error(request, "Объект не создан: нужны название и заказчик.")
            return self.get(request, *args, **kwargs)
        site = ServiceObject(
            subsystem=subsystem,
            code=_next_number(ServiceObject, subsystem, "OB-"),
            customer=form.cleaned_data["customer"],
        )
        for field in _JOB_FIELDS:
            setattr(site, field, form.cleaned_data[field])
        site.save()
        messages.success(request, f"Объект {site.code} открыт.")
        return redirect("service-object", pk=site.pk)


class ServiceObjectDetailView(ServiceContourMixin, TemplateView):
    module_code = "S02"
    template_name = "platform/service/object.html"
    page_title = "Объект"

    def _site(self):
        return get_object_or_404(
            ServiceObject.objects.select_related("customer"),
            pk=self.kwargs["pk"],
            subsystem=self.subsystem(),
        )

    def _employees(self):
        return get_user_model().objects.filter(
            subsystem_memberships__subsystem=self.subsystem()
        ).distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        site = self._site()
        context.update(
            {
                "site": site,
                "form": ObjectForm(
                    subsystem=site.subsystem,
                    initial={
                        "title": site.title,
                        "address": site.address,
                        "city": site.city,
                        "state": site.state,
                        "job_type": site.job_type,
                        "placement": site.placement,
                        "width_ft": site.width_ft,
                        "height_ft": site.height_ft,
                        "event_on": site.event_on,
                        "stage": site.stage,
                        "status": site.status,
                        "notes": site.notes,
                        "customer": site.customer_id,
                    },
                ),
                "visit_form": VisitForm(employees=self._employees()),
                "force_form": DeploymentForm(),
                "visits": [
                    {"item": visit, "form": _visit_form(visit, self._employees())}
                    for visit in site.visits.select_related("employee")
                ],
                "forces": [
                    {"item": row, "form": _force_form(row)} for row in site.deployments.all()
                ],
                "totals": object_totals(site),
            }
        )
        context["page_title"] = site.title
        return context

    def post(self, request, *args, **kwargs):
        site = self._site()
        action = request.POST.get("action") or "save"
        if action == "save":
            form = ObjectForm(request.POST, subsystem=site.subsystem)
            if form.is_valid():
                site.customer = form.cleaned_data["customer"]
                for field in _JOB_FIELDS:
                    setattr(site, field, form.cleaned_data[field])
                site.save()
                messages.success(request, "Карточка объекта сохранена.")
            else:
                messages.error(request, "Карточка объекта не сохранена.")
        elif action == "visit":
            form = VisitForm(request.POST, employees=self._employees())
            if form.is_valid():
                ServiceVisit.objects.create(
                    subsystem=site.subsystem,
                    site=site,
                    **form.cleaned_data,
                )
                messages.success(request, "Выезд посчитан и записан на объект.")
            else:
                messages.error(request, "Выезд не записан: проверьте сотрудника, дату и ставки.")
        elif action == "visit_save":
            visit = get_object_or_404(ServiceVisit, pk=request.POST.get("visit_id"), site=site)
            form = VisitForm(request.POST, employees=self._employees(), prefix=f"v{visit.pk}")
            if form.is_valid():
                for field, value in form.cleaned_data.items():
                    setattr(visit, field, value)
                visit.save()
                messages.success(request, "Выезд пересчитан.")
            else:
                messages.error(request, "Выезд не сохранён: проверьте дату и ставки.")
        elif action == "visit_delete":
            ServiceVisit.objects.filter(pk=request.POST.get("visit_id"), site=site).delete()
            messages.success(request, "Выезд снят с объекта.")
        elif action == "resource":
            form = DeploymentForm(request.POST)
            if form.is_valid():
                ServiceDeployment.objects.create(
                    subsystem=site.subsystem,
                    site=site,
                    **form.cleaned_data,
                )
                messages.success(request, "Силы и средства списаны на объект.")
            else:
                messages.error(request, "Строка сил не записана.")
        elif action == "resource_save":
            row = get_object_or_404(ServiceDeployment, pk=request.POST.get("resource_id"), site=site)
            form = DeploymentForm(request.POST, prefix=f"f{row.pk}")
            if form.is_valid():
                for field, value in form.cleaned_data.items():
                    setattr(row, field, value)
                row.save()
                messages.success(request, "Строка сил пересчитана.")
            else:
                messages.error(request, "Строка сил не сохранена.")
        elif action == "resource_delete":
            ServiceDeployment.objects.filter(pk=request.POST.get("resource_id"), site=site).delete()
            messages.success(request, "Строка сил снята с объекта.")
        return redirect("service-object", pk=site.pk)


def _visit_form(visit: ServiceVisit, employees) -> VisitForm:
    return VisitForm(
        employees=employees,
        prefix=f"v{visit.pk}",
        initial={
            "employee": visit.employee_id,
            "departed_on": visit.departed_on,
            "distance_mi": visit.distance_mi,
            "rate_per_mile": visit.rate_per_mile,
            "hours": visit.hours,
            "hour_rate": visit.hour_rate,
            "other_cost": visit.other_cost,
            "note": visit.note,
        },
    )


def _force_form(row: ServiceDeployment) -> DeploymentForm:
    return DeploymentForm(
        prefix=f"f{row.pk}",
        initial={
            "kind": row.kind,
            "title": row.title,
            "quantity": row.quantity,
            "unit": row.unit,
            "unit_cost": row.unit_cost,
            "note": row.note,
        },
    )


def save_new_customer(request, subsystem):
    form = CustomerForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Карточка не открыта: проверьте имя заказчика.")
        return None
    customer = ServiceCustomer(
        subsystem=subsystem,
        number=_next_number(ServiceCustomer, subsystem, "ZK-"),
    )
    form.apply(customer)
    ensure_deal(customer)
    messages.success(request, f"Карточка {customer.number} открыта.")
    return customer


def _deal_initial(deal: ServiceDeal) -> dict:
    return {
        field: getattr(deal, field)
        for field in (
            "title",
            "stage",
            "job_type",
            "source",
            "city",
            "state",
            "venue",
            "placement",
            "width_ft",
            "height_ft",
            "timeline",
            "event_on",
            "value",
            "decision_maker",
            "screen_over_30",
            "guests_over_200",
            "church_project",
            "lost_reason",
        )
    }


def _deal_form(deal: ServiceDeal) -> DealForm:
    return DealForm(
        subsystem=deal.subsystem,
        lock_customer=True,
        prefix=f"d{deal.pk}",
        initial=_deal_initial(deal),
    )


def _customer_initial(customer: ServiceCustomer) -> dict:
    return {
        "display_name": customer.display_name,
        "company": customer.company,
        "phone": customer.phone,
        "email": customer.email,
        "address": customer.address,
        "city": customer.city,
        "state": customer.state,
        "stage": customer.stage,
        "payment_state": customer.payment_state,
        "invoice_amount": customer.invoice_amount,
        "tags": customer.tags,
        "notes": customer.notes,
    }
