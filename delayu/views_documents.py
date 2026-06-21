"""M05 — Документы: реестр, мастер загрузки, версии, карточка, подпись."""
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import TemplateView

from delayu.forms_documents import DocumentVersionForm, DocumentWizardForm
from delayu.mixins import ModulePermissionMixin
from delayu.models import DocumentFile
from delayu.services import audit
from delayu.services.access import user_can
from delayu.services.documents import (
    create_document,
    document_card_context,
    sign_document,
    upload_new_version,
)
from delayu.views_platform import _ctx_membership


class DocumentsListView(ModulePermissionMixin, TemplateView):
    module_code = "M05"
    template_name = "platform/documents/list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Документы"
        qs = DocumentFile.objects.filter(
            subsystem=m.subsystem, is_current=True
        ).select_related("case", "uploaded_by")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
        doc_type = self.request.GET.get("type", "")
        if doc_type:
            qs = qs.filter(doc_type=doc_type)
        signed = self.request.GET.get("signed")
        if signed == "1":
            qs = qs.filter(is_signed=True)
        elif signed == "0":
            qs = qs.filter(is_signed=False)
        case_id = self.request.GET.get("case")
        if case_id:
            qs = qs.filter(case_id=case_id)
        ctx["documents"] = qs.order_by("-created_at")[:100]
        ctx["search_q"] = q
        ctx["filter_type"] = doc_type
        ctx["filter_signed"] = signed or ""
        ctx["filter_case"] = case_id or ""
        ctx["doc_types"] = DocumentFile.DocType.choices
        ctx["can_create"] = user_can(self.request.user, "M05", "create")
        ctx["can_change"] = user_can(self.request.user, "M05", "change")
        ctx["can_delete"] = user_can(self.request.user, "M05", "delete")
        return ctx


class DocumentWizardCreateView(ModulePermissionMixin, TemplateView):
    module_code = "M05"
    required_action = "create"
    template_name = "platform/documents/wizard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Загрузка документа"
        ctx["form"] = kwargs.get("form") or DocumentWizardForm(subsystem=m.subsystem)
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = DocumentWizardForm(request.POST, request.FILES, subsystem=m.subsystem)
        if form.is_valid():
            from delayu.services.upload_validation import validate_upload

            ok, err = validate_upload(form.cleaned_data.get("file"))
            if not ok:
                messages.error(request, err)
                return self.render_to_response(self.get_context_data(form=form))
            doc = create_document(
                subsystem=m.subsystem,
                user=request.user,
                title=form.cleaned_data["title"],
                doc_type=form.cleaned_data["doc_type"],
                description=form.cleaned_data.get("description"),
                case=form.cleaned_data.get("case"),
                file=form.cleaned_data["file"],
            )
            from delayu.services.documents import find_duplicate_documents

            dupes = find_duplicate_documents(m.subsystem, doc.content_sha256, exclude_pk=doc.pk)
            if dupes.exists():
                other = dupes.first()
                messages.warning(
                    request,
                    f"Файл с таким SHA-256 уже есть: «{other.title}» (v{other.version}).",
                )
            from delayu.models import AvScanResult

            scan = doc.av_scans.order_by("-created_at").first()
            if scan and scan.status == AvScanResult.Status.INFECTED:
                messages.warning(
                    request,
                    f"Внимание: антивирус (M79) — {scan.get_status_display()}: {scan.threat_name}",
                )
            elif scan:
                messages.info(request, f"Антивирус (M79): {scan.get_status_display()}.")
            audit.log_action(
                request.user,
                m.subsystem,
                "document.create",
                "DocumentFile",
                doc.pk,
                {"version": 1},
                request,
            )
            messages.success(request, f"Документ «{doc.title}» загружен.")
            return redirect(f"/documents/?open={doc.pk}")
        return self.render_to_response(self.get_context_data(form=form))


class DocumentModalView(ModulePermissionMixin, View):
    module_code = "M05"

    def get(self, request, pk):
        m = _ctx_membership(self)
        doc = get_object_or_404(DocumentFile, pk=pk, subsystem=m.subsystem)
        ctx = document_card_context(doc)
        ctx["can_change"] = user_can(request.user, "M05", "change")
        ctx["can_create"] = user_can(request.user, "M05", "create")
        ctx["version_form"] = DocumentVersionForm()
        return render(request, "platform/documents/_modal_body.html", ctx)


class DocumentVersionUploadView(ModulePermissionMixin, View):
    module_code = "M05"
    required_action = "create"

    def post(self, request, pk):
        m = _ctx_membership(self)
        doc = get_object_or_404(DocumentFile, pk=pk, subsystem=m.subsystem)
        form = DocumentVersionForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                new_doc = upload_new_version(
                    doc,
                    request.user,
                    form.cleaned_data["file"],
                    title=form.cleaned_data.get("title") or None,
                )
                from delayu.models import AvScanResult

                scan = new_doc.av_scans.order_by("-created_at").first()
                if scan and scan.status == AvScanResult.Status.INFECTED:
                    messages.warning(request, f"Антивирус: угроза {scan.threat_name}")
                audit.log_action(
                    request.user,
                    m.subsystem,
                    "document.version",
                    "DocumentFile",
                    new_doc.pk,
                    {"version": new_doc.version},
                    request,
                )
                messages.success(request, f"Создана версия {new_doc.version}.")
                return redirect(f"/documents/?open={new_doc.pk}")
            except ValueError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, "Выберите файл.")
        return redirect(f"/documents/?open={pk}")


class DocumentSignView(ModulePermissionMixin, View):
    module_code = "M05"
    required_action = "change"

    def post(self, request, pk):
        m = _ctx_membership(self)
        doc = get_object_or_404(DocumentFile, pk=pk, subsystem=m.subsystem, is_current=True)
        try:
            sign_document(doc, request.user)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect(f"/documents/?open={pk}")
        audit.log_action(
            request.user, m.subsystem, "document.sign", "DocumentFile", doc.pk, request=request
        )
        messages.success(request, "Документ отмечен как подписанный (демо КЭП).")
        return redirect(f"/documents/?open={pk}")


class DocumentDeleteView(ModulePermissionMixin, View):
    module_code = "M05"
    required_action = "delete"

    def post(self, request, pk):
        m = _ctx_membership(self)
        doc = get_object_or_404(DocumentFile, pk=pk, subsystem=m.subsystem)
        root = doc.get_root()
        if doc.case_id and doc.case.is_archived:
            messages.error(request, "Нельзя удалить документ архивного дела.")
            return redirect("platform-documents")
        from delayu.services.documents import _q_root

        count = DocumentFile.objects.filter(_q_root(root.pk)).count()
        DocumentFile.objects.filter(_q_root(root.pk)).delete()
        audit.log_action(
            request.user,
            m.subsystem,
            "document.delete",
            "DocumentFile",
            pk,
            {"versions": count},
            request,
        )
        messages.success(request, "Документ и все версии удалены.")
        return redirect("platform-documents")
