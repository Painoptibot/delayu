"""M42–M45 — интеграции, REST, СМЭВ, внешние ИС."""
import json

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import TemplateView

from delayu.forms_integrations import (
    ApiKeyForm,
    ExternalSyncForm,
    IntegrationEndpointForm,
    SmevSendForm,
)
from delayu.mixins import ModulePermissionMixin
from delayu.models import ApiClientKey, IntegrationEndpoint, IntegrationMessage
from delayu.services import audit
from delayu.services.access import user_can
from delayu.services.integrations import (
    create_api_key,
    enqueue_outbound,
    filter_endpoints,
    filter_messages,
    hub_metrics,
    move_to_dead_letter,
    openapi_spec,
    process_outbound,
    process_pending_queue,
    queue_metrics,
    receive_inbound,
    retry_message,
)
from delayu.views_platform import _ctx_membership


class IntegrationHubView(ModulePermissionMixin, TemplateView):
    module_code = "M42"
    template_name = "platform/integrations/hub.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Шлюз интеграций"
        ctx["metrics"] = hub_metrics(m.subsystem)
        ctx["endpoints"] = filter_endpoints(m.subsystem)[:12]
        ctx["messages"] = filter_messages(m.subsystem, {})[:15]
        ctx["integrations_tab"] = "hub"
        ctx["can_create"] = user_can(self.request.user, "M42", "create")
        from delayu.services.integration_registry import external_services_for_subsystem

        ctx["external_services"] = external_services_for_subsystem(m.subsystem)
        sub_code = m.subsystem.code
        ctx["integration_api_hints"] = [
            {
                "title": "Входящее обращение (ЕПГУ)",
                "method": "POST",
                "path": f"/api/v1/integration/inbound/{sub_code}/epgu_uzhv/",
                "auth": "X-Integration-Secret: uzhv-epgu-demo-secret",
            },
            {
                "title": "Заявление из МФЦ (I-07)",
                "method": "POST",
                "path": f"/api/v1/integration/inbound/{sub_code}/mfc_uzhv/",
                "auth": "X-Integration-Secret: uzhv-mfc-demo-secret",
            },
            {
                "title": "1С — учётное дело (JSON)",
                "method": "POST",
                "path": f"/api/v1/integration/inbound/{sub_code}/external_1c_uzhv/",
                "auth": "X-Integration-Secret: uzhv-1c-demo-secret",
            },
            {
                "title": "Telegram Bot webhook",
                "method": "POST",
                "path": f"/api/v1/telegram/{sub_code}/",
                "auth": "X-Telegram-Bot-Api-Secret-Token",
            },
            {
                "title": "Публичная форма (браузер)",
                "method": "GET/POST",
                "path": f"/public/{sub_code}/appeal/",
                "auth": "без входа (UZHV_PUBLIC_APPEAL_TOKEN опционально)",
            },
        ]
        ctx["free_integrations_doc"] = "docs/integrations-free.md"
        if m.subsystem.industry_template == "uzhv":
            from delayu.services.integration_tz_matrix import tz_integration_options

            ctx["tz_integrations"] = tz_integration_options()
        return ctx


class IntegrationEndpointsView(ModulePermissionMixin, TemplateView):
    module_code = "M42"
    template_name = "platform/integrations/endpoints.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Коннекторы"
        ctx["endpoints"] = filter_endpoints(m.subsystem, params=self.request.GET)
        ctx["integrations_tab"] = "endpoints"
        ctx["can_create"] = user_can(self.request.user, "M42", "create")
        return ctx


class IntegrationEndpointCreateView(ModulePermissionMixin, TemplateView):
    module_code = "M42"
    required_action = "create"
    template_name = "platform/integrations/endpoint_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Новый коннектор"
        ctx["form"] = kwargs.get("form") or IntegrationEndpointForm()
        ctx["integrations_tab"] = "endpoints"
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = IntegrationEndpointForm(request.POST)
        if form.is_valid():
            ep = form.save(commit=False)
            ep.subsystem = m.subsystem
            ep.save()
            audit.log_action(
                request.user, m.subsystem, "integration.create", "IntegrationEndpoint", ep.pk, request=request
            )
            messages.success(request, f"Коннектор «{ep.name}» создан.")
            return redirect("platform-integration-endpoints")
        return self.render_to_response(self.get_context_data(form=form))


class IntegrationMessagesView(ModulePermissionMixin, TemplateView):
    module_code = "M42"
    template_name = "platform/integrations/messages.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Журнал обменов"
        ctx["messages"] = filter_messages(m.subsystem, self.request.GET)[:100]
        ctx["endpoints"] = filter_endpoints(m.subsystem)
        ctx["filter_status"] = self.request.GET.get("status", "")
        ctx["filter_endpoint"] = self.request.GET.get("endpoint", "")
        ctx["status_choices"] = IntegrationMessage.Status.choices
        ctx["integrations_tab"] = "messages"
        ctx["queue_metrics"] = queue_metrics(m.subsystem)
        ctx["can_change"] = user_can(self.request.user, "M42", "change")
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        action = request.POST.get("action", "")
        if action == "process_queue" and user_can(request.user, "M42", "change"):
            result = process_pending_queue(m.subsystem)
            audit.log_action(
                request.user,
                m.subsystem,
                "integration.queue.process",
                "IntegrationMessage",
                "",
                result,
                request,
            )
            messages.info(
                request,
                f"Очередь: обработано {result['processed']}, успех {result['success']}, ошибок {result['failed']}.",
            )
        return redirect("platform-integrations-messages")


class IntegrationMessageModalView(ModulePermissionMixin, View):
    module_code = "M42"

    def get(self, request, pk):
        m = _ctx_membership(self)
        msg = get_object_or_404(
            IntegrationMessage, pk=pk, endpoint__subsystem=m.subsystem
        )
        return render(
            request,
            "platform/integrations/_message_modal.html",
            {"msg": msg, "payload_json": json.dumps(msg.payload, ensure_ascii=False, indent=2)},
        )


class IntegrationSendView(ModulePermissionMixin, View):
    module_code = "M42"
    required_action = "create"

    def post(self, request, pk):
        m = _ctx_membership(self)
        ep = get_object_or_404(IntegrationEndpoint, pk=pk, subsystem=m.subsystem)
        msg = enqueue_outbound(
            ep,
            {"demo": True, "user": request.user.username},
            external_id=request.POST.get("external_id", ""),
        )
        process_outbound(msg)
        messages.success(request, f"Сообщение {msg.get_status_display().lower()}.")
        return redirect("platform-integrations-messages")


class IntegrationRetryView(ModulePermissionMixin, View):
    module_code = "M42"
    required_action = "change"

    def post(self, request, pk):
        m = _ctx_membership(self)
        msg = get_object_or_404(
            IntegrationMessage, pk=pk, endpoint__subsystem=m.subsystem
        )
        retry_message(msg)
        messages.success(request, "Повторная отправка выполнена.")
        return redirect("platform-integrations-messages")


class IntegrationDeadLetterView(ModulePermissionMixin, View):
    module_code = "M42"
    required_action = "change"

    def post(self, request, pk):
        m = _ctx_membership(self)
        msg = get_object_or_404(
            IntegrationMessage, pk=pk, endpoint__subsystem=m.subsystem
        )
        move_to_dead_letter(msg, reason=request.POST.get("reason", ""))
        audit.log_action(
            request.user,
            m.subsystem,
            "integration.dead_letter",
            "IntegrationMessage",
            msg.pk,
            request=request,
        )
        messages.warning(request, "Сообщение перенесено в dead letter.")
        return redirect("platform-integrations-messages")


class ApiDocsView(ModulePermissionMixin, TemplateView):
    module_code = "M43"
    template_name = "platform/integrations/api_docs.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "REST / OpenAPI"
        ctx["spec"] = openapi_spec()
        ctx["spec_json"] = json.dumps(openapi_spec(), ensure_ascii=False, indent=2)
        ctx["keys"] = ApiClientKey.objects.filter(subsystem=m.subsystem).order_by("-created_at")
        ctx["integrations_tab"] = "api"
        ctx["can_create"] = user_can(self.request.user, "M43", "create")
        ctx["new_api_key"] = self.request.session.pop("last_api_key_plain", None)
        return ctx


class ApiKeyCreateView(ModulePermissionMixin, TemplateView):
    module_code = "M43"
    required_action = "create"
    template_name = "platform/integrations/api_key_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Новый API-ключ"
        ctx["form"] = kwargs.get("form") or ApiKeyForm()
        ctx["integrations_tab"] = "api"
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = ApiKeyForm(request.POST)
        if form.is_valid():
            obj, raw = create_api_key(
                subsystem=m.subsystem,
                name=form.cleaned_data["name"],
                rate_limit=form.cleaned_data["rate_limit_per_hour"],
            )
            request.session["last_api_key_plain"] = raw
            messages.success(request, "Ключ создан. Скопируйте его сейчас — повторно не показывается.")
            return redirect("platform-api-docs")
        return self.render_to_response(self.get_context_data(form=form))


class ApiOpenApiJsonView(ModulePermissionMixin, View):
    module_code = "M43"

    def get(self, request):
        return JsonResponse(openapi_spec())


class SmevHubView(ModulePermissionMixin, TemplateView):
    module_code = "M44"
    template_name = "platform/integrations/smev.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "СМЭВ"
        ctx["endpoints"] = filter_endpoints(
            m.subsystem, endpoint_type=IntegrationEndpoint.EndpointType.SMEV
        )
        ctx["messages"] = filter_messages(m.subsystem, {}).filter(
            endpoint__endpoint_type=IntegrationEndpoint.EndpointType.SMEV
        )[:30]
        ctx["form"] = SmevSendForm()
        ctx["integrations_tab"] = "smev"
        ctx["can_create"] = user_can(self.request.user, "M44", "create")
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        ep_id = request.POST.get("endpoint_id")
        ep = get_object_or_404(
            IntegrationEndpoint,
            pk=ep_id,
            subsystem=m.subsystem,
            endpoint_type=IntegrationEndpoint.EndpointType.SMEV,
        )
        form = SmevSendForm(request.POST)
        if form.is_valid():
            msg = enqueue_outbound(
                ep,
                {
                    "message_type": form.cleaned_data["message_type"],
                    "body": form.cleaned_data["body"],
                },
            )
            process_outbound(msg)
            messages.success(request, "Запрос поставлен в очередь СМЭВ.")
        return redirect("platform-smev")


class SmevReceiveView(ModulePermissionMixin, View):
    module_code = "M44"
    required_action = "create"

    def post(self, request, pk):
        m = _ctx_membership(self)
        ep = get_object_or_404(
            IntegrationEndpoint,
            pk=pk,
            subsystem=m.subsystem,
            endpoint_type=IntegrationEndpoint.EndpointType.SMEV,
        )
        receive_inbound(
            ep,
            {"demo_response": True, "status": "OK", "message": "Демо-ответ СМЭВ"},
        )
        messages.success(request, "Входящее сообщение СМЭВ зарегистрировано.")
        return redirect("platform-smev")


class ExternalConnectorsView(ModulePermissionMixin, TemplateView):
    module_code = "M45"
    template_name = "platform/integrations/external.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        external_types = [
            IntegrationEndpoint.EndpointType.EXTERNAL_1C,
            IntegrationEndpoint.EndpointType.EXTERNAL_GIS,
            IntegrationEndpoint.EndpointType.MAIL,
        ]
        ctx["page_title"] = "Внешние информационные системы"
        ctx["endpoints"] = filter_endpoints(m.subsystem, endpoint_type=external_types)
        ctx["messages"] = filter_messages(m.subsystem, {}).filter(
            endpoint__endpoint_type__in=external_types
        )[:20]
        ctx["form"] = ExternalSyncForm()
        ctx["integrations_tab"] = "external"
        ctx["can_create"] = user_can(self.request.user, "M45", "create")
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        ep_id = request.POST.get("endpoint_id")
        ep = get_object_or_404(IntegrationEndpoint, pk=ep_id, subsystem=m.subsystem)
        form = ExternalSyncForm(request.POST)
        if form.is_valid():
            mapping = ep.config.get("field_mapping", {})
            msg = enqueue_outbound(
                ep,
                {
                    "entity": form.cleaned_data["entity"],
                    "external_id": form.cleaned_data["external_id"],
                    "field_mapping": mapping,
                },
            )
            process_outbound(msg)
            messages.success(request, "Синхронизация запущена (демо).")
        return redirect("platform-external")


# Совместимость URL platform-integrations
class IntegrationsView(IntegrationHubView):
    pass
