"""Плейбуки видов работ и очередь дня."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import TemplateView

from delayu.models_service import ServiceCustomer, ServicePlaybook
from delayu.services.service_deals import create_deal
from delayu.services.service_dialogue import ServiceFlowError
from delayu.services.service_follow import clone_playbook, escalate_overdue, save_norms, save_route
from delayu.services.service_process import add_job_type, ensure_process, queue_snapshot
from delayu.views_service import ServiceContourMixin


class ServicePlaybookView(ServiceContourMixin, TemplateView):
    module_code = "S01"
    template_name = "platform/service/playbooks.html"
    page_title = "Плейбуки"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        subsystem = self.subsystem()
        ensure_process(subsystem)
        books = list(subsystem.service_playbooks.all())
        titles = {row.code: row.title for row in subsystem.service_job_types.all()}
        context["books"] = [
            {"book": book, "title": titles.get(book.job_type, book.name)} for book in books
        ]
        context["customers"] = ServiceCustomer.objects.filter(subsystem=subsystem)
        context["reasons"] = subsystem.service_reasons.all()
        return context

    def post(self, request, *args, **kwargs):
        subsystem = self.subsystem()
        action = request.POST.get("action") or "type"
        try:
            if action == "clone":
                book = get_object_or_404(
                    ServicePlaybook, pk=request.POST.get("book_id"), subsystem=subsystem
                )
                fresh = clone_playbook(book, request.POST.get("code") or "", request.POST.get("title") or "")
                messages.success(request, f"Плейбук «{fresh.name}» скопирован в тот же контур.")
                return redirect("service-playbooks")
            if action == "route":
                route = save_route(
                    subsystem,
                    job_type=request.POST.get("job_type") or "sale",
                    province=request.POST.get("province") or "",
                    owner_name=request.POST.get("owner_name") or "",
                )
                messages.success(request, f"{route.province}: {route.owner_name}.")
                return redirect("service-playbooks")
            if action == "norms":
                book = get_object_or_404(
                    ServicePlaybook, pk=request.POST.get("book_id"), subsystem=subsystem
                )
                save_norms(
                    book,
                    stale_days=request.POST.get("stale_days") or 7,
                    warranty_days=request.POST.get("warranty_days") or 0,
                    approval_amount=request.POST.get("approval_amount") or 0,
                    after_hours=request.POST.get("after_hours") or "",
                )
                messages.success(request, f"Нормы «{book.name}» сохранены.")
                return redirect("service-playbooks")
            if action == "deal":
                customer = get_object_or_404(
                    ServiceCustomer, pk=request.POST.get("customer"), subsystem=subsystem
                )
                deal = create_deal(
                    customer=customer,
                    title=(request.POST.get("title") or customer.display_name)[:255],
                    stage=ServiceCustomer.Stage.NEW_LEAD,
                    job_type=(request.POST.get("job_type") or "sale")[:16],
                    source="playbook",
                )
                messages.success(request, f"{deal.number}: вид работ {deal.job_type}, карточка та же.")
                return redirect("service-customer", pk=customer.pk)
            book = add_job_type(
                subsystem,
                request.POST.get("code") or "",
                request.POST.get("title") or "",
            )
        except ServiceFlowError as exc:
            messages.error(request, str(exc))
            return redirect("service-playbooks")
        messages.success(request, f"Плейбук «{book.name}» в том же контуре.")
        return redirect("service-playbooks")


class ServiceQueueView(ServiceContourMixin, TemplateView):
    module_code = "S01"
    template_name = "platform/service/queue.html"
    page_title = "Очередь дня"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        role = self.request.GET.get("role") or "manager"
        if role not in {"manager", "sales", "dispatcher"}:
            role = "manager"
        context.update(queue_snapshot(self.subsystem(), role))
        context["role_label"] = {
            "manager": "Руководитель видит всё",
            "sales": "Продавец видит дела",
            "dispatcher": "Диспетчер видит площадки и выезды",
        }[role]
        return context

    def post(self, request, *args, **kwargs):
        made = escalate_overdue(self.subsystem())
        messages.success(request, f"Эскалаций поставлено: {made}.")
        return redirect("service-queue")
