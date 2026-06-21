"""Интерактивные мастера создания сущностей АИС УЖВ."""
from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from delayu.forms_uzhv import (
    HousingAppealRegisterForm,
    HousingCitizenForm,
    HousingQueueCaseForm,
    MunicipalBuildingForm,
)
from delayu.forms_uzhv_wizard import UzhvChainWizardForm
from delayu.mixins import ModulePermissionMixin
from delayu.models_uzhv import HousingAppeal, HousingCitizen, HousingQueueCase
from delayu.services.access import user_can
from delayu.services.uzhv import next_case_number, register_housing_appeal
from delayu.services.uzhv_queue import recalculate_housing_queue
from delayu.views_uzhv import UzhvSubsystemMixin, _can


def _wizard_ctx(extra=None):
    ctx = {"wizard_cancel_url": reverse("uzhv-create-hub")}
    if extra:
        ctx.update(extra)
    return ctx


class UzhvCreateHubView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/create_hub.html"
    page_title = "Мастер создания"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx["can_m22"] = _can(user, "create")
        ctx["can_m24"] = user_can(user, "M24", "create")
        cards = []
        if ctx["can_m22"]:
            cards.extend(
                [
                    {
                        "title": "Полная цепочка",
                        "desc": "Гражданин → дело → обращение за один проход",
                        "icon": "ri-links-line",
                        "url": reverse("uzhv-create-chain"),
                        "accent": "primary",
                    },
                    {
                        "title": "Гражданин",
                        "desc": "ФИО, документы, контакты (DaData)",
                        "icon": "ri-user-add-line",
                        "url": reverse("uzhv-citizen-create"),
                    },
                    {
                        "title": "Учётное дело",
                        "desc": "Постановка на учёт, категория, исполнитель",
                        "icon": "ri-folder-add-line",
                        "url": reverse("uzhv-case-create"),
                    },
                    {
                        "title": "МКД",
                        "desc": "Адрес, кадастр, карта",
                        "icon": "ri-building-2-line",
                        "url": reverse("uzhv-building-create"),
                    },
                ]
            )
        if ctx["can_m24"]:
            cards.append(
                {
                    "title": "Обращение",
                    "desc": "Регистрация с SLA 30 дней и M24",
                    "icon": "ri-mail-add-line",
                    "url": reverse("uzhv-appeal-create"),
                }
            )
        ctx["create_cards"] = cards
        return ctx


class UzhvCitizenWizardCreateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/wizard_citizen.html"
    page_title = "Новый гражданин"
    required_action = "create"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            _wizard_ctx(
                {
                    "wizard_subtitle": "Шаги: персональные данные → документы → контакты",
                    "form": kwargs.get("form") or HousingCitizenForm(),
                    "wizard_cancel_url": reverse("uzhv-citizens"),
                }
            )
        )
        return ctx

    def post(self, request, *args, **kwargs):
        sub = self.get_subsystem()
        form = HousingCitizenForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.subsystem = sub
            obj.save()
            messages.success(request, f"Гражданин {obj.full_name} добавлен")
            return redirect(reverse("uzhv-citizens") + f"?open={obj.pk}")
        return self.render_to_response(self.get_context_data(form=form))


class UzhvCaseWizardCreateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/wizard_case.html"
    page_title = "Новое учётное дело"
    required_action = "create"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        initial = {
            "case_number": next_case_number(sub),
            "registered_at": timezone.now().date(),
        }
        citizen_id = self.request.GET.get("citizen")
        if citizen_id:
            initial["citizen"] = citizen_id
        ctx.update(
            _wizard_ctx(
                {
                    "wizard_subtitle": "Шаги: заявитель → учёт → исполнение",
                    "form": kwargs.get("form")
                    or HousingQueueCaseForm(subsystem=sub, initial=initial),
                    "wizard_cancel_url": reverse("uzhv-cases"),
                }
            )
        )
        return ctx

    def post(self, request, *args, **kwargs):
        sub = self.get_subsystem()
        form = HousingQueueCaseForm(request.POST, subsystem=sub)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.subsystem = sub
            obj.save()
            from delayu.services.uzhv_case_status import record_case_status_change

            record_case_status_change(
                obj,
                old_status="",
                new_status=obj.status,
                user=request.user,
                comment="Создание дела (мастер)",
            )
            if obj.status in (
                HousingQueueCase.Status.REGISTERED,
                HousingQueueCase.Status.QUEUED,
            ):
                recalculate_housing_queue(sub)
            messages.success(request, f"Дело {obj.case_number} создано")
            return redirect(reverse("uzhv-cases") + f"?open={obj.pk}")
        return self.render_to_response(self.get_context_data(form=form))


class UzhvAppealWizardCreateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    module_code = "M24"
    template_name = "platform/uzhv/wizard_appeal.html"
    page_title = "Регистрация обращения"
    required_action = "create"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        initial = {"received_at": timezone.now().date()}
        if self.request.GET.get("citizen"):
            initial["citizen"] = self.request.GET["citizen"]
        if self.request.GET.get("case"):
            initial["housing_case"] = self.request.GET["case"]
        ctx.update(
            _wizard_ctx(
                {
                    "wizard_subtitle": "Шаги: заявитель → содержание → исполнение",
                    "form": kwargs.get("form")
                    or HousingAppealRegisterForm(subsystem=sub, initial=initial),
                    "sla_days": HousingAppeal.SLA_DAYS,
                    "wizard_cancel_url": reverse("uzhv-appeals"),
                }
            )
        )
        return ctx

    def post(self, request):
        sub = self.get_subsystem()
        form = HousingAppealRegisterForm(request.POST, subsystem=sub)
        if form.is_valid():
            data = form.cleaned_data
            appeal = register_housing_appeal(
                subsystem=sub,
                user=request.user,
                subject=data["subject"],
                body=data.get("body") or "",
                citizen=data.get("citizen"),
                housing_case=data.get("housing_case"),
                assignee=data.get("assignee"),
                received_at=data["received_at"],
            )
            messages.success(
                request,
                f"Обращение {appeal.appeal_number} зарегистрировано. "
                f"Срок ответа: {appeal.due_date:%d.%m.%Y}",
            )
            return redirect(reverse("uzhv-appeals") + f"?open={appeal.pk}")
        return self.render_to_response(self.get_context_data(form=form))


class UzhvBuildingWizardCreateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/wizard_building.html"
    page_title = "Новый МКД"
    required_action = "create"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            _wizard_ctx(
                {
                    "wizard_subtitle": "Шаги: адрес → характеристики → карта",
                    "form": kwargs.get("form") or MunicipalBuildingForm(),
                    "wizard_cancel_url": reverse("uzhv-fund"),
                }
            )
        )
        return ctx

    def post(self, request, *args, **kwargs):
        sub = self.get_subsystem()
        form = MunicipalBuildingForm(request.POST)
        if form.is_valid():
            building = form.save(commit=False)
            building.subsystem = sub
            building.save()
            messages.success(request, "МКД добавлен")
            return redirect(reverse("uzhv-fund") + f"?open={building.pk}")
        return self.render_to_response(self.get_context_data(form=form))


class UzhvChainWizardCreateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/wizard_chain.html"
    page_title = "Цепочка: гражданин → дело → обращение"
    required_action = "create"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        initial = {"received_at": timezone.now().date()}
        ctx.update(
            _wizard_ctx(
                {
                    "wizard_subtitle": "Один мастер для типового сценария приёма",
                    "form": kwargs.get("form")
                    or UzhvChainWizardForm(subsystem=sub, initial=initial),
                    "can_appeal": user_can(self.request.user, "M24", "create"),
                }
            )
        )
        return ctx

    def post(self, request, *args, **kwargs):
        sub = self.get_subsystem()
        form = UzhvChainWizardForm(request.POST, subsystem=sub)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))

        data = form.cleaned_data
        if data["citizen_mode"] == UzhvChainWizardForm.MODE_EXISTING:
            citizen = data["existing_citizen"]
        else:
            citizen = HousingCitizen.objects.create(
                subsystem=sub,
                last_name=data["last_name"].strip(),
                first_name=data["first_name"].strip(),
                middle_name=(data.get("middle_name") or "").strip(),
                snils=(data.get("snils") or "").strip(),
                phone=(data.get("phone") or "").strip(),
                reg_address=(data.get("reg_address") or "").strip(),
            )

        case = None
        if data.get("create_case"):
            case = HousingQueueCase.objects.create(
                subsystem=sub,
                citizen=citizen,
                case_number=next_case_number(sub),
                category=data["case_category"],
                status=data["case_status"],
                registered_at=timezone.now().date(),
                assignee=data.get("case_assignee"),
            )
            from delayu.services.uzhv_case_status import record_case_status_change

            record_case_status_change(
                case,
                old_status="",
                new_status=case.status,
                user=request.user,
                comment="Создание из мастера цепочки",
            )
            if case.status in (
                HousingQueueCase.Status.REGISTERED,
                HousingQueueCase.Status.QUEUED,
            ):
                recalculate_housing_queue(sub)

        appeal = None
        if data.get("create_appeal") and user_can(request.user, "M24", "create"):
            appeal = register_housing_appeal(
                subsystem=sub,
                user=request.user,
                subject=data["appeal_subject"],
                body=data.get("appeal_body") or "",
                citizen=citizen,
                housing_case=case,
                assignee=data.get("appeal_assignee"),
                received_at=data["received_at"],
            )

        parts = [f"Гражданин {citizen.full_name}"]
        if case:
            parts.append(f"дело {case.case_number}")
        if appeal:
            parts.append(f"обращение {appeal.appeal_number}")
        messages.success(request, "Создано: " + ", ".join(parts))

        if appeal:
            return redirect(reverse("uzhv-appeals") + f"?open={appeal.pk}")
        if case:
            return redirect(reverse("uzhv-cases") + f"?open={case.pk}")
        return redirect(reverse("uzhv-citizens") + f"?open={citizen.pk}")
