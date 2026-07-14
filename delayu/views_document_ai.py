"""API и UI: OCR + предзаполнение (M51 / AI-P0-03, AI-P0-04)."""
import json

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView

from delayu.mixins import ModulePermissionMixin
from delayu.models import DocumentFile
from delayu.models_uzhv import HousingCaseAttachment, HousingQueueCase
from delayu.services import audit
from delayu.services.ai_gateway import AiGatewayError
from delayu.services.document_intelligence import apply_uzhv_fields, recognize_with_gateway
from delayu.views_platform import _ctx_membership
from delayu.views_uzhv import UzhvSubsystemMixin


class DocumentOcrPreviewView(ModulePermissionMixin, View):
    """POST: распознавание файла документа M05 (JSON)."""

    module_code = "M51"
    required_action = "view"

    def post(self, request, pk):
        m = _ctx_membership(request)
        doc = get_object_or_404(DocumentFile, pk=pk, subsystem=m.subsystem)
        if not doc.file:
            return JsonResponse({"error": "Нет файла"}, status=400)
        try:
            result = recognize_with_gateway(
                m.subsystem,
                request.user,
                doc.file,
                filename=doc.file.name,
                module_code="M51",
            )
        except AiGatewayError as exc:
            return JsonResponse({"error": exc.message, "code": exc.code}, status=429)
        audit.log_action(
            request.user,
            m.subsystem,
            "ai.ocr.preview",
            "DocumentFile",
            doc.pk,
            {"engine": result["engine"], "fields": result["field_count"]},
            request,
        )
        return JsonResponse(result)


class UzhvAttachmentOcrPreviewView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    module_code = "M51"
    required_action = "view"

    def post(self, request, pk, att_pk):
        sub = self.get_subsystem()
        case = get_object_or_404(HousingQueueCase, pk=pk, subsystem=sub)
        att = get_object_or_404(HousingCaseAttachment, pk=att_pk, case=case)
        if not att.file:
            return JsonResponse({"error": "Нет файла"}, status=400)
        try:
            result = recognize_with_gateway(
                sub,
                request.user,
                att.file,
                filename=att.file.name,
                module_code="M51",
            )
        except AiGatewayError as exc:
            return JsonResponse({"error": exc.message, "code": exc.code}, status=429)
        audit.log_action(
            request.user,
            sub,
            "ai.ocr.preview",
            "HousingCaseAttachment",
            att.pk,
            {"case_id": case.pk, "engine": result["engine"], "fields": result["field_count"]},
            request,
        )
        return JsonResponse(result)


class UzhvOcrApplyView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    """POST JSON: применить подтверждённые поля к гражданину / делу (HITL)."""

    module_code = "M51"
    required_action = "change"

    def post(self, request, pk):
        sub = self.get_subsystem()
        case = get_object_or_404(
            HousingQueueCase.objects.select_related("citizen"),
            pk=pk,
            subsystem=sub,
        )
        try:
            body = json.loads(request.body.decode("utf-8") if request.body else "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Некорректный JSON"}, status=400)

        fields = body.get("fields") or {}
        if not isinstance(fields, dict) or not fields:
            return JsonResponse({"error": "Не выбраны поля для применения"}, status=400)

        changes = apply_uzhv_fields(case, case.citizen, fields, user=request.user)

        from delayu.services.ai_hitl import create_review

        review = create_review(
            subsystem=sub,
            user=request.user,
            title=f"OCR → дело {case.case_number}",
            ai_output=json.dumps(fields, ensure_ascii=False)[:4000],
            module_code="M51",
        )
        from delayu.services.ai_hitl import approve_review

        approve_review(review, reviewer=request.user, comment="Подтверждено при применении OCR")

        return JsonResponse({"ok": True, "changes": changes, "review_id": review.pk})


class AiOcrPageView(ModulePermissionMixin, TemplateView):
    """Страница OCR с загрузкой файла."""

    module_code = "M51"
    template_name = "platform/ai/ocr.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "OCR и извлечение реквизитов"
        ctx["ai_tab"] = "tools"
        ctx["ocr_result"] = self.request.session.pop("ocr_page_result", None)
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(request)
        upload = request.FILES.get("file")
        if not upload:
            messages.error(request, "Выберите файл")
            return redirect("platform-ai-ocr")
        try:
            result = recognize_with_gateway(
                m.subsystem,
                request.user,
                upload,
                filename=upload.name,
                module_code="M51",
            )
        except AiGatewayError as exc:
            messages.error(request, exc.message)
            return redirect("platform-ai-ocr")
        request.session["ocr_page_result"] = result
        messages.success(
            request,
            f"Распознано полей: {result['field_count']}, движок: {result['engine']}",
        )
        return redirect("platform-ai-ocr")


class AiModuleDocView(ModulePermissionMixin, TemplateView):
    """Документ «Модуль ИИ» для экспертизы реестра (AI-P0-12)."""

    module_code = "M47"
    template_name = "platform/ai/module_doc.html"

    def get_context_data(self, **kwargs):
        from delayu.services.registry_platform import build_ai_module_doc

        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Модуль «Интеллектуальная обработка данных»"
        ctx["ai_tab"] = "module"
        ctx["doc"] = build_ai_module_doc(m.subsystem)
        return ctx


class AiModuleDocExportView(ModulePermissionMixin, View):
    module_code = "M47"

    def get(self, request):
        from delayu.services.registry_platform import export_ai_module_pdf

        m = _ctx_membership(request)
        return export_ai_module_pdf(m.subsystem)
