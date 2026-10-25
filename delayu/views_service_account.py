"""Поля, формы, телефония, переписка, задачи и отчёт воронки."""
from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import TemplateView

from delayu.models_service import ServiceCustomer, ServiceDeal, ServiceForm, ServiceMessage, ServiceTask
from delayu.services.service_intake import open_form_lead
from delayu.services.service_process import report_slices
from delayu.services.service_snapshot import load_canadian_led
from delayu.views_service import ServiceContourMixin


class ServiceFieldListView(ServiceContourMixin, TemplateView):
    module_code = "S01"
    template_name = "platform/service/fields.html"
    page_title = "Свои поля"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        load_canadian_led(self.subsystem())
        context["fields"] = self.subsystem().service_fields.all()
        context["field_count"] = context["fields"].count()
        context["folders"] = (
            self.subsystem().service_fields.exclude(folder="").values_list("folder", flat=True).distinct().count()
        )
        return context


class ServiceFormListView(ServiceContourMixin, TemplateView):
    module_code = "S01"
    template_name = "platform/service/forms.html"
    page_title = "Формы"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        load_canadian_led(self.subsystem())
        context["forms"] = self.subsystem().service_forms.all()
        return context

    def post(self, request, *args, **kwargs):
        form = get_object_or_404(ServiceForm, pk=request.POST.get("form_id"), subsystem=self.subsystem())
        name = (request.POST.get("display_name") or "").strip()
        email = (request.POST.get("email") or "").strip()
        if email and "@" not in email:
            messages.error(request, "Заявка не открыта: почта записана не целиком.")
            return redirect("service-forms")
        if form.status != ServiceForm.Status.ACTIVE:
            messages.error(request, "Черновик заявку не открывает.")
            return redirect("service-forms")
        if not name:
            messages.error(request, "Заявка не открыта: нужно имя.")
            return redirect("service-forms")
        customer, deal = open_form_lead(
            subsystem=self.subsystem(),
            form_name=form.name,
            display_name=name,
            phone=request.POST.get("phone") or "",
            email=email,
            message=request.POST.get("message") or "",
        )
        messages.success(request, f"{form.name}: {customer.number}, сделка {deal.number}.")
        return redirect("service-customer", pk=customer.pk)


class ServiceInboxView(ServiceContourMixin, TemplateView):
    module_code = "S01"
    template_name = "platform/service/inbox.html"
    page_title = "Переписка"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["thread"] = (
            ServiceMessage.objects.filter(subsystem=self.subsystem())
            .select_related("customer")
            .order_by("-created_at", "-pk")[:80]
        )
        return context


class ServiceTaskListView(ServiceContourMixin, TemplateView):
    module_code = "S01"
    template_name = "platform/service/tasks.html"
    page_title = "Задачи"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tasks"] = self.subsystem().service_tasks.select_related("customer", "deal")
        return context

    def post(self, request, *args, **kwargs):
        task = get_object_or_404(ServiceTask, pk=request.POST.get("task_id"), subsystem=self.subsystem())
        task.done = not task.done
        task.save(update_fields=["done"])
        messages.success(request, "Задача обновлена.")
        return redirect("service-tasks")


class ServiceReportView(ServiceContourMixin, TemplateView):
    module_code = "S01"
    template_name = "platform/service/report.html"
    page_title = "Отчёт воронки"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        subsystem = self.subsystem()
        deals = ServiceDeal.objects.filter(subsystem=subsystem)
        rows = []
        for code, label in ServiceCustomer.Stage.choices:
            bucket = deals.filter(stage=code).exclude(status=ServiceDeal.Status.LOST)
            rows.append(
                {
                    "label": label,
                    "count": bucket.count(),
                    "value": bucket.aggregate(total=Sum("value"))["total"] or 0,
                }
            )
        lost = deals.filter(status=ServiceDeal.Status.LOST)
        rows.append(
            {
                "label": "Lost",
                "count": lost.count(),
                "value": lost.aggregate(total=Sum("value"))["total"] or 0,
            }
        )
        context["rows"] = rows
        context["open_tasks"] = ServiceTask.objects.filter(subsystem=subsystem, done=False).count()
        context["messages"] = ServiceMessage.objects.filter(subsystem=subsystem).count()
        context["customers"] = ServiceCustomer.objects.filter(subsystem=subsystem).count()
        context.update(report_slices(subsystem))
        return context


class ServicePhoneListView(ServiceContourMixin, TemplateView):
    module_code = "S01"
    template_name = "platform/service/phones.html"
    page_title = "Телефония и люди"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        load_canadian_led(self.subsystem())
        context["phones"] = self.subsystem().service_phones.all()
        context["staff"] = self.subsystem().service_staff.all()
        return context
