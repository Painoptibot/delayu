"""M24–M32 — корреспонденция, журнал, маршрутизация, печать, ЭП, сканирование."""
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, TemplateView

from delayu.forms_correspondence import (
    CorrespondenceRouteForm,
    InboundRegisterForm,
    OutboundRegisterForm,
    PrintTemplateForm,
    ScanBatchForm,
)
from delayu.mixins import MethodActionPermissionMixin, ModulePermissionMixin
from delayu.models import Correspondence, CorrespondenceEvent, DocumentFile, PrintTemplate, SignatureRequest
from delayu.services import ai, audit
from delayu.services.access import user_can
from delayu.services.correspondence import (
    filter_correspondence,
    log_event,
    register_inbound_enhanced,
    register_correspondence,
    render_print_template,
    route_correspondence,
)
from delayu.services.documents import create_document, sign_document
from delayu.services.signatures import complete_signature, create_signature_request, send_to_signing
from delayu.services.workplace import log_activity
from delayu.views_platform import _ctx_membership


def _corr_module(corr: Correspondence) -> str:
    return "M24" if corr.direction == Correspondence.Direction.IN else "M25"


def _correspondence_folder_qs(subsystem, folder: str, params):
    """Фильтр списка писем по папке (как в шаблоне app-email)."""
    qs = filter_correspondence(subsystem, params=params)
    folder = (folder or "inbox").strip()
    if folder == "trash":
        return qs.filter(is_deleted=True)
    qs = qs.filter(is_deleted=False)
    if folder == "spam":
        return qs.filter(is_spam=True)
    if folder == "draft":
        return qs.filter(is_draft=True)
    if folder == "starred":
        return qs.filter(is_starred=True, is_spam=False)
    if folder == "sent":
        return qs.filter(
            direction=Correspondence.Direction.OUT, is_draft=False, is_spam=False
        )
    return qs.filter(
        direction=Correspondence.Direction.IN, is_draft=False, is_spam=False
    )


class InboxListView(ModulePermissionMixin, TemplateView):
    """Единый почтовый интерфейс: входящие, исходящие, метки (M24/M25)."""

    module_code = "M24"
    template_name = "platform/correspondence/inbox.html"
    paginate_by = 25

    def dispatch(self, request, *args, **kwargs):
        folder = request.GET.get("folder", "inbox")
        if folder == "sent":
            if not user_can(request.user, "M25", "view") and not user_can(
                request.user, "M24", "view"
            ):
                from django.core.exceptions import PermissionDenied

                raise PermissionDenied("Нет доступа к исходящим")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        folder = self.request.GET.get("folder", "inbox")
        qs = _correspondence_folder_qs(m.subsystem, folder, self.request.GET)
        from django.core.paginator import Paginator

        paginator = Paginator(qs, self.paginate_by)
        ctx["page_obj"] = paginator.get_page(self.request.GET.get("page", 1))
        ctx["items"] = ctx["page_obj"]
        titles = {
            "inbox": "Входящие",
            "sent": "Исходящие",
            "draft": "Черновики",
            "starred": "Избранное",
            "spam": "Спам",
            "trash": "Корзина",
        }
        ctx["page_title"] = titles.get(folder, "Корреспонденция")
        ctx["mail_folder"] = folder
        ctx["search_q"] = self.request.GET.get("q", "")
        ctx["filter_status"] = self.request.GET.get("status", "")
        ctx["status_choices"] = Correspondence.Status.choices
        ctx["can_create_in"] = user_can(self.request.user, "M24", "create")
        ctx["can_create_out"] = user_can(self.request.user, "M25", "create")
        ctx["can_change"] = user_can(self.request.user, "M24", "change") or user_can(
            self.request.user, "M25", "change"
        )
        ctx["nav_active"] = "outbox" if folder == "sent" else "inbox"
        return ctx


class OutboxListView(ModulePermissionMixin, TemplateView):
    """Старый URL — редирект в единый почтовый интерфейс."""

    module_code = "M25"

    def get(self, request, *args, **kwargs):
        params = request.GET.copy()
        params["folder"] = "sent"
        return redirect(f"{reverse('platform-inbox')}?{params.urlencode()}")


class JournalListView(ModulePermissionMixin, TemplateView):
    module_code = "M26"
    template_name = "platform/correspondence/journal.html"
    paginate_by = 30

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        qs = filter_correspondence(m.subsystem, params=self.request.GET).select_related(
            "journal_entry", "journal_entry__operator"
        )
        direction = self.request.GET.get("direction", "").strip()
        if direction in (Correspondence.Direction.IN, Correspondence.Direction.OUT):
            qs = qs.filter(direction=direction)
        from django.core.paginator import Paginator

        paginator = Paginator(qs, self.paginate_by)
        ctx["page_obj"] = paginator.get_page(self.request.GET.get("page", 1))
        ctx["items"] = ctx["page_obj"]
        ctx["page_title"] = "Журнал регистрации"
        ctx["search_q"] = self.request.GET.get("q", "")
        ctx["filter_direction"] = direction
        ctx["filter_year"] = self.request.GET.get("year", "")
        ctx["nav_active"] = "journal"
        return ctx


class InboundRegisterView(MethodActionPermissionMixin, TemplateView):
    module_code = "M24"
    template_name = "platform/correspondence/wizard_inbound.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Регистрация входящего"
        ctx["form"] = kwargs.get("form") or InboundRegisterForm(subsystem=m.subsystem)
        ctx["nav_active"] = "inbox"
        ctx["classify_preview_url"] = reverse("platform-inbound-classify-preview")
        ctx["can_create"] = user_can(self.request.user, "M24", "create")
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = InboundRegisterForm(request.POST, subsystem=m.subsystem)
        if form.is_valid():
            corr, linked_case, ai_hint = register_inbound_enhanced(
                subsystem=m.subsystem,
                organization=m.organization,
                user=request.user,
                subject=form.cleaned_data["subject"],
                counterparty=form.cleaned_data["counterparty"],
                assignee=form.cleaned_data.get("assignee"),
                case=form.cleaned_data.get("case"),
                status=form.cleaned_data["status"],
                reg_date=form.cleaned_data["reg_date"],
                create_case=form.cleaned_data.get("create_case"),
                new_case_title=form.cleaned_data.get("new_case_title", ""),
            )
            audit.log_action(
                request.user,
                m.subsystem,
                "correspondence.register",
                "Correspondence",
                corr.pk,
                {"reg_number": corr.reg_number, "case_id": linked_case.pk if linked_case else None},
                request,
            )
            audit.log_action(
                request.user,
                m.subsystem,
                "ai.classify",
                "Correspondence",
                corr.pk,
                ai_hint,
                request,
            )
            log_activity(
                m.subsystem,
                request.user,
                "registered",
                corr.reg_number,
                module_code="M24",
                link_path=reverse("platform-correspondence-detail", kwargs={"pk": corr.pk}),
            )
            msg = f"Зарегистрировано {corr.reg_number}"
            if linked_case and form.cleaned_data.get("create_case"):
                msg += f"; создано дело {linked_case.number}"
            messages.success(request, msg)
            return redirect("platform-correspondence-detail", pk=corr.pk)
        return self.render_to_response(self.get_context_data(form=form))


class InboundClassifyPreviewView(ModulePermissionMixin, View):
    """#35 — AJAX-подсказка классификации при регистрации входящего."""

    module_code = "M24"
    required_action = "view"

    def get(self, request):
        subject = (request.GET.get("subject") or "").strip()
        if len(subject) < 3:
            return JsonResponse({"detail": "subject_too_short"}, status=400)
        result = ai.classify_correspondence(subject)
        return JsonResponse(result)


class OutboundRegisterView(MethodActionPermissionMixin, TemplateView):
    module_code = "M25"
    template_name = "platform/correspondence/wizard_outbound.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Регистрация исходящего"
        ctx["form"] = kwargs.get("form") or OutboundRegisterForm(subsystem=m.subsystem)
        ctx["nav_active"] = "outbox"
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = OutboundRegisterForm(request.POST, subsystem=m.subsystem)
        if form.is_valid():
            corr = register_correspondence(
                subsystem=m.subsystem,
                user=request.user,
                direction=Correspondence.Direction.OUT,
                subject=form.cleaned_data["subject"],
                counterparty=form.cleaned_data["counterparty"],
                assignee=form.cleaned_data.get("assignee"),
                case=form.cleaned_data.get("case"),
                status=form.cleaned_data["status"],
                reg_date=form.cleaned_data["reg_date"],
                linked_incoming=form.cleaned_data.get("linked_incoming"),
            )
            audit.log_action(
                request.user,
                m.subsystem,
                "correspondence.register",
                "Correspondence",
                corr.pk,
                {"reg_number": corr.reg_number, "direction": "out"},
                request,
            )
            log_activity(
                m.subsystem,
                request.user,
                "registered",
                corr.reg_number,
                module_code="M25",
                link_path=reverse("platform-correspondence-detail", kwargs={"pk": corr.pk}),
            )
            messages.success(request, f"Зарегистрировано {corr.reg_number}")
            return redirect("platform-correspondence-detail", pk=corr.pk)
        return self.render_to_response(self.get_context_data(form=form))


class CorrespondenceDetailView(ModulePermissionMixin, DetailView):
    module_code = "M24"
    model = Correspondence
    template_name = "platform/correspondence/detail.html"
    context_object_name = "corr"

    def dispatch(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        corr = get_object_or_404(
            Correspondence, pk=kwargs["pk"], subsystem=m.subsystem
        )
        self.module_code = _corr_module(corr)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return Correspondence.objects.filter(
            subsystem=_ctx_membership(self).subsystem
        ).select_related("assignee", "case", "linked_incoming", "created_by")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        c = self.object
        ctx["module_code"] = _corr_module(c)
        ctx["routes"] = c.routes.select_related("from_user", "to_user")[:20]
        ctx["events"] = c.events.select_related("actor", "document")[:15]
        ctx["route_form"] = CorrespondenceRouteForm(
            subsystem=_ctx_membership(self).subsystem
        )
        ctx["can_route"] = user_can(self.request.user, "M27", "change")
        ctx["can_change"] = user_can(
            self.request.user, _corr_module(c), "change"
        )
        ctx["print_templates"] = PrintTemplate.objects.filter(
            subsystem=c.subsystem, is_active=True
        )
        ctx["documents"] = DocumentFile.objects.filter(
            subsystem=c.subsystem, case=c.case, is_current=True
        )[:20] if c.case_id else []
        ctx["nav_active"] = "inbox" if c.direction == Correspondence.Direction.IN else "outbox"
        return ctx


class CorrespondenceModalView(ModulePermissionMixin, View):
    """Фрагмент для AJAX (совместимость)."""

    module_code = "M24"

    def dispatch(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        corr = get_object_or_404(
            Correspondence, pk=kwargs["pk"], subsystem=m.subsystem
        )
        self.module_code = _corr_module(corr)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, pk):
        corr = get_object_or_404(
            Correspondence, pk=pk, subsystem=_ctx_membership(self).subsystem
        )
        return render(
            request,
            "platform/correspondence/_modal_body.html",
            {"corr": corr, "can_change": user_can(request.user, self.module_code, "change")},
        )


class CorrespondenceEmailPanelView(ModulePermissionMixin, View):
    """JSON + HTML для панели просмотра письма (как app-email)."""

    module_code = "M24"

    def dispatch(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        corr = get_object_or_404(
            Correspondence, pk=kwargs["pk"], subsystem=m.subsystem
        )
        self.module_code = _corr_module(corr)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, pk):
        corr = get_object_or_404(
            Correspondence, pk=pk, subsystem=_ctx_membership(self).subsystem
        )
        if not corr.is_read:
            corr.is_read = True
            corr.save(update_fields=["is_read"])
        from delayu.forms_correspondence import CorrespondenceRouteForm

        m = _ctx_membership(self)
        html = render_to_string(
            "platform/correspondence/_email_view_panel.html",
            {
                "corr": corr,
                "route_form": CorrespondenceRouteForm(subsystem=m.subsystem),
                "can_route": user_can(request.user, "M27", "change"),
            },
            request=request,
        )
        return JsonResponse(
            {
                "title": corr.subject or corr.reg_number,
                "status": corr.get_status_display(),
                "html": html,
            }
        )


class CorrespondenceMailActionsView(ModulePermissionMixin, View):
    """Массовые действия над письмами: удаление, прочитано, метки."""

    module_code = "M24"
    required_action = "change"

    def post(self, request):
        m = _ctx_membership(self)
        action = (request.POST.get("action") or "").strip()
        raw_ids = request.POST.getlist("ids") or (request.POST.get("ids") or "").split(",")
        ids = [int(x) for x in raw_ids if str(x).strip().isdigit()]
        if not ids or not action:
            return JsonResponse({"ok": False, "error": "Нет выбранных писем"}, status=400)

        qs = Correspondence.objects.filter(subsystem=m.subsystem, pk__in=ids)
        updated = 0
        label = (request.POST.get("label") or "").strip()

        for corr in qs:
            mod = _corr_module(corr)
            if not user_can(request.user, mod, "change"):
                continue
            if action == "delete":
                corr.is_deleted = True
                corr.deleted_at = timezone.now()
                corr.save(update_fields=["is_deleted", "deleted_at"])
            elif action == "restore":
                corr.is_deleted = False
                corr.save(update_fields=["is_deleted"])
            elif action == "mark_read":
                corr.is_read = True
                corr.save(update_fields=["is_read"])
            elif action == "mark_unread":
                corr.is_read = False
                corr.save(update_fields=["is_read"])
            elif action == "star":
                corr.is_starred = True
                corr.save(update_fields=["is_starred"])
            elif action == "unstar":
                corr.is_starred = False
                corr.save(update_fields=["is_starred"])
            elif action == "spam":
                corr.is_spam = True
                corr.save(update_fields=["is_spam"])
            elif action == "label" and label in dict(Correspondence.MailLabel.choices):
                corr.mail_label = label
                corr.save(update_fields=["mail_label"])
            elif action == "clear_label":
                corr.mail_label = ""
                corr.save(update_fields=["mail_label"])
            else:
                continue
            updated += 1

        if updated == 0:
            return JsonResponse({"ok": False, "error": "Нет прав или неизвестное действие"}, status=403)
        return JsonResponse({"ok": True, "updated": updated})


class CorrespondenceRouteView(ModulePermissionMixin, View):
    module_code = "M27"
    required_action = "change"

    def post(self, request, pk):
        m = _ctx_membership(self)
        corr = get_object_or_404(Correspondence, pk=pk, subsystem=m.subsystem)
        form = CorrespondenceRouteForm(request.POST, subsystem=m.subsystem)
        if form.is_valid():
            route_correspondence(
                corr,
                request.user,
                form.cleaned_data["to_user"],
                form.cleaned_data.get("comment", ""),
            )
            audit.log_action(
                request.user,
                m.subsystem,
                "correspondence.route",
                "Correspondence",
                corr.pk,
                request=request,
            )
            messages.success(request, "Корреспонденция передана исполнителю.")
        else:
            messages.error(request, "Укажите получателя.")
        return redirect("platform-correspondence-detail", pk=pk)


class CorrespondenceCompleteView(ModulePermissionMixin, View):
    """Закрыть корреспонденцию и отправить уведомления по маршруту СЭД."""

    module_code = "M27"
    required_action = "change"

    def post(self, request, pk):
        m = _ctx_membership(self)
        corr = get_object_or_404(Correspondence, pk=pk, subsystem=m.subsystem)
        from delayu.services.notify_dispatch import notify_correspondence_closed

        notify_correspondence_closed(corr, request.user)
        log_event(
            corr,
            CorrespondenceEvent.EventType.STATUS,
            "Маршрут завершён, статус «Закрыто»",
            actor=request.user,
        )
        messages.success(request, "Корреспонденция закрыта. Уведомления отправлены.")
        return redirect("platform-correspondence-detail", pk=pk)


class CorrespondenceHistoryView(ModulePermissionMixin, TemplateView):
    module_code = "M28"
    template_name = "platform/correspondence/history.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        corr = get_object_or_404(Correspondence, pk=self.kwargs["pk"], subsystem=m.subsystem)
        ctx["corr"] = corr
        ctx["events"] = corr.events.select_related("actor", "document").order_by("-created_at")
        if corr.case_id:
            docs = DocumentFile.objects.filter(case=corr.case, subsystem=m.subsystem)
            ctx["doc_versions"] = (
                DocumentFile.objects.filter(
                    Q(pk__in=docs.values_list("pk", flat=True))
                    | Q(root_document_id__in=docs.values_list("pk", flat=True))
                )
                .select_related("uploaded_by")
                .order_by("-created_at")[:50]
            )
        else:
            ctx["doc_versions"] = []
        ctx["nav_active"] = "journal"
        return ctx


class PrintTemplateListView(ModulePermissionMixin, TemplateView):
    module_code = "M29"
    template_name = "platform/correspondence/print_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Печатные формы"
        ctx["templates"] = PrintTemplate.objects.filter(subsystem=m.subsystem).order_by("code")
        ctx["can_create"] = user_can(self.request.user, "M29", "create")
        ctx["nav_active"] = "print"
        return ctx


class PrintTemplateCreateView(ModulePermissionMixin, TemplateView):
    module_code = "M29"
    required_action = "create"
    template_name = "platform/correspondence/print_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Новая печатная форма"
        ctx["form"] = kwargs.get("form") or PrintTemplateForm()
        ctx["nav_active"] = "print"
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = PrintTemplateForm(request.POST)
        if form.is_valid():
            tpl = form.save(commit=False)
            tpl.subsystem = m.subsystem
            tpl.save()
            messages.success(request, "Шаблон сохранён.")
            return redirect("platform-print-templates")
        return self.render_to_response(self.get_context_data(form=form))


class PrintTemplatePreviewView(ModulePermissionMixin, TemplateView):
    module_code = "M29"
    template_name = "platform/correspondence/print_preview.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        tpl = get_object_or_404(PrintTemplate, pk=self.kwargs["pk"], subsystem=m.subsystem)
        corr_id = self.request.GET.get("correspondence")
        corr = None
        rendered = tpl.body
        if corr_id:
            corr = Correspondence.objects.filter(pk=corr_id, subsystem=m.subsystem).first()
            if corr:
                rendered = render_print_template(tpl, corr)
        ctx["template"] = tpl
        ctx["corr"] = corr
        ctx["rendered"] = rendered
        ctx["nav_active"] = "print"
        return ctx


class SignatureCenterView(ModulePermissionMixin, TemplateView):
    module_code = "M30"
    template_name = "platform/correspondence/signatures.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Центр электронной подписи"
        ctx["unsigned"] = DocumentFile.objects.filter(
            subsystem=m.subsystem, is_current=True, is_signed=False
        ).select_related("case")[:100]
        ctx["signed_recent"] = DocumentFile.objects.filter(
            subsystem=m.subsystem, is_current=True, is_signed=True
        ).order_by("-created_at")[:20]
        ctx["signature_requests"] = SignatureRequest.objects.filter(
            document__subsystem=m.subsystem
        ).select_related("document", "requester")[:30]
        ctx["can_sign"] = user_can(self.request.user, "M30", "change") or user_can(
            self.request.user, "M05", "change"
        )
        ctx["nav_active"] = "signatures"
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        if not (
            user_can(request.user, "M30", "change")
            or user_can(request.user, "M05", "change")
        ):
            messages.error(request, "Нет прав на подписание.")
            return redirect("platform-signatures")
        ids = request.POST.getlist("doc_ids")
        action = request.POST.get("action", "sign_local")
        if action == "kep_request":
            created = 0
            for doc_id in ids:
                doc = DocumentFile.objects.filter(
                    pk=doc_id, subsystem=m.subsystem, is_current=True, is_signed=False
                ).first()
                if not doc:
                    continue
                req = create_signature_request(document=doc, requester=request.user)
                send_to_signing(req)
                created += 1
                audit.log_action(
                    request.user,
                    m.subsystem,
                    "signature.request",
                    "SignatureRequest",
                    req.pk,
                    {"document_id": doc.pk},
                    request,
                )
            messages.success(request, f"Запросов КЭП создано: {created}.")
            return redirect("platform-signatures")
        signed = 0
        for doc_id in ids:
            doc = DocumentFile.objects.filter(
                pk=doc_id, subsystem=m.subsystem, is_current=True
            ).first()
            if not doc or doc.is_signed:
                continue
            try:
                sign_document(doc, request.user)
                signed += 1
                for corr in Correspondence.objects.filter(case=doc.case_id)[:5]:
                    log_event(
                        corr,
                        CorrespondenceEvent.EventType.SIGNED,
                        f"Подписан документ «{doc.title}»",
                        actor=request.user,
                        document=doc,
                    )
            except ValueError:
                pass
        messages.success(request, f"Подписано документов: {signed}.")
        return redirect("platform-signatures")


class SignatureRequestCompleteView(ModulePermissionMixin, View):
    module_code = "M30"
    required_action = "change"

    def post(self, request, pk):
        m = _ctx_membership(self)
        req = get_object_or_404(
            SignatureRequest, pk=pk, document__subsystem=m.subsystem
        )
        complete_signature(req, user=request.user)
        audit.log_action(
            request.user,
            m.subsystem,
            "signature.complete",
            "SignatureRequest",
            req.pk,
            {"status": req.status},
            request,
        )
        messages.success(request, f"Статус КЭП: {req.get_status_display()}.")
        return redirect("platform-signatures")


class GoskeyStubView(ModulePermissionMixin, TemplateView):
    module_code = "M31"
    template_name = "platform/correspondence/goskey.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Госключ и внешние УЦ"
        ctx["nav_active"] = "goskey"
        return ctx


class ScanBatchView(ModulePermissionMixin, TemplateView):
    module_code = "M32"
    required_action = "create"
    template_name = "platform/correspondence/scan_batch.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Пакетное сканирование"
        ctx["form"] = kwargs.get("form") or ScanBatchForm(subsystem=m.subsystem)
        ctx["nav_active"] = "scan"
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = ScanBatchForm(request.POST, subsystem=m.subsystem)
        files = request.FILES.getlist("files")
        if not files:
            messages.error(request, "Выберите один или несколько файлов.")
            return self.render_to_response(self.get_context_data(form=form))
        case = None
        if request.POST.get("case"):
            from delayu.models import CaseFile

            case = CaseFile.objects.filter(
                pk=request.POST.get("case"), subsystem=m.subsystem
            ).first()
        count = 0
        for f in files:
            create_document(
                subsystem=m.subsystem,
                user=request.user,
                title=f.name[:200],
                doc_type=DocumentFile.DocType.SCAN,
                description="Пакетная загрузка (M32)",
                case=case,
                file=f,
            )
            count += 1
        audit.log_action(
            request.user,
            m.subsystem,
            "scan.batch",
            "DocumentFile",
            0,
            {"count": count},
            request,
        )
        messages.success(request, f"Загружено файлов: {count}.")
        return redirect("platform-documents")
