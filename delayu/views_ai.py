"""M47–M66 — ИИ-хаб и инструменты."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from delayu.forms_ai import (
    AiPolicyForm,
    AiQuestionForm,
    AiSearchForm,
    CaseAiToolForm,
    ClassifyForm,
    KnowledgeArticleForm,
    NerForm,
)
from delayu.mixins import ModulePermissionMixin
from delayu.models import AiFeedback, AiHumanReview, AiRequestLog, CaseFile, KnowledgeArticle
from delayu.services import ai
from delayu.services.access import user_can
from delayu.views_platform import _ctx_membership


class AiHubView(ModulePermissionMixin, TemplateView):
    module_code = "M47"
    template_name = "platform/ai/hub.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Искусственный интеллект"
        ctx["ai_tab"] = "hub"
        ctx["logs_today"] = ai.ai_usage_today(m.subsystem)
        ctx["policy"] = ai.get_or_create_policy(m.subsystem)
        ctx["recent_logs"] = AiRequestLog.objects.filter(subsystem=m.subsystem)[:8]
        ctx["recent_feedback"] = AiFeedback.objects.filter(subsystem=m.subsystem)[:5]
        ctx["pending_reviews"] = AiHumanReview.objects.filter(
            subsystem=m.subsystem, status=AiHumanReview.Status.PENDING
        )[:5]
        return ctx


class AiAssistantView(ModulePermissionMixin, TemplateView):
    module_code = "M47"
    template_name = "platform/ai/assistant.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "ИИ-ассистент"
        ctx["ai_tab"] = "assistant"
        ctx["form"] = AiQuestionForm()
        ctx["answer"] = self.request.session.pop("ai_last_answer", None)
        ctx["logs"] = AiRequestLog.objects.filter(
            subsystem=m.subsystem, module_code="M47", user=self.request.user
        )[:10]
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = AiQuestionForm(request.POST)
        if form.is_valid():
            request.session["ai_last_answer"] = ai.assistant_chat(
                m.subsystem, request.user, form.cleaned_data["question"]
            )
        return redirect("platform-ai-assistant")


class AiSearchView(ModulePermissionMixin, TemplateView):
    module_code = "M48"
    template_name = "platform/ai/search.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Семантический поиск"
        ctx["ai_tab"] = "search"
        ctx["form"] = AiSearchForm(initial={"q": self.request.GET.get("q", "")})
        q = self.request.GET.get("q", "").strip()
        ctx["query"] = q
        if q:
            from delayu.services.ai_gateway import AiGatewayError, invoke

            def run():
                hits = ai.semantic_search(m.subsystem, q)
                return f"{len(hits)} hits"

            try:
                invoke(m.subsystem, self.request.user, "M48", q, run)
            except AiGatewayError as exc:
                ctx["gateway_error"] = exc.message
            ctx["results"] = ai.semantic_search(m.subsystem, q)
        return ctx


class KnowledgeListView(ModulePermissionMixin, TemplateView):
    module_code = "M61"
    template_name = "platform/ai/knowledge.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "База знаний"
        ctx["ai_tab"] = "knowledge"
        ctx["articles"] = KnowledgeArticle.objects.filter(subsystem=m.subsystem)
        ctx["can_create"] = user_can(self.request.user, "M61", "create")
        return ctx


class KnowledgeCreateView(ModulePermissionMixin, TemplateView):
    module_code = "M61"
    required_action = "create"
    template_name = "platform/ai/knowledge_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Новая статья"
        ctx["form"] = kwargs.get("form") or KnowledgeArticleForm()
        ctx["ai_tab"] = "knowledge"
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = KnowledgeArticleForm(request.POST)
        if form.is_valid():
            art = form.save(commit=False)
            art.subsystem = m.subsystem
            art.save()
            messages.success(request, "Статья сохранена.")
            return redirect("platform-knowledge")
        return self.render_to_response(self.get_context_data(form=form))


class AiToolsView(ModulePermissionMixin, TemplateView):
    """M49–M56, M59–M60, M63–M65 — панель инструментов."""
    module_code = "M47"
    template_name = "platform/ai/tools.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Инструменты ИИ"
        ctx["ai_tab"] = "tools"
        ctx["case_form"] = CaseAiToolForm(subsystem=m.subsystem)
        ctx["classify_form"] = ClassifyForm()
        ctx["ner_form"] = NerForm()
        ctx["tool"] = self.request.GET.get("tool", "case")
        case = None
        if self.request.GET.get("case"):
            case = CaseFile.objects.filter(
                pk=self.request.GET.get("case"), subsystem=m.subsystem
            ).first()
        ctx["selected_case"] = case
        if case:
            ctx["summary"] = ai.summarize_case(case)
            ctx["risk"] = ai.risk_overdue(case)
            ctx["completeness"] = ai.case_completeness(case)
            ctx["due_prediction"] = ai.predict_due_date(case)
            ctx["bpm_hint"] = ai.suggest_bpm_step(case)
        ctx["tool_result"] = self.request.session.pop("ai_tool_result", None)
        ctx["classify_detail"] = self.request.session.pop("ai_classify_detail", None)
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        tool = request.POST.get("tool", "case")
        if tool == "classify":
            form = ClassifyForm(request.POST)
            if form.is_valid():
                subject = form.cleaned_data["subject"]
                result = ai.classify_correspondence(subject)
                result["subject"] = subject
                request.session["ai_classify_detail"] = result
                from delayu.services import audit

                audit.log_action(
                    request.user,
                    m.subsystem,
                    "ai.classify",
                    "Correspondence",
                    "",
                    {"subject": subject[:120], **result},
                    request,
                )
                from delayu.services.ai_hitl import create_review

                create_review(
                    subsystem=m.subsystem,
                    user=request.user,
                    title=f"Классификация: {result['theme']}",
                    ai_output=str(result),
                    module_code="M49",
                )
                ai._log(
                    m.subsystem,
                    request.user,
                    "M49",
                    subject,
                    str(result),
                )
        elif tool == "ner":
            form = NerForm(request.POST)
            if form.is_valid():
                result = ai.extract_entities(form.cleaned_data["text"])
                request.session["ai_tool_result"] = str(result)
                ai._log(
                    m.subsystem,
                    request.user,
                    "M50",
                    form.cleaned_data["text"][:100],
                    str(result),
                )
        elif tool == "sentiment":
            text = request.POST.get("text", "")
            result = ai.sentiment(text)
            request.session["ai_tool_result"] = str(result)
            ai._log(m.subsystem, request.user, "M63", text[:100], str(result))
        elif tool == "qa":
            q = request.POST.get("question", "")
            ans = ai.qa_regulations(m.subsystem, q)
            request.session["ai_tool_result"] = ans
            ai._log(m.subsystem, request.user, "M59", q, ans[:200])
        return redirect(f"/ai/tools/?tool={tool}")


class AiPoliciesView(ModulePermissionMixin, TemplateView):
    module_code = "M66"
    template_name = "platform/ai/policies.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Политики и журнал ИИ"
        ctx["ai_tab"] = "policies"
        policy = ai.get_or_create_policy(m.subsystem)
        ctx["form"] = kwargs.get("form") or AiPolicyForm(instance=policy)
        ctx["policy"] = policy
        ctx["usage_today"] = ai.ai_usage_today(m.subsystem)
        ctx["logs"] = AiRequestLog.objects.filter(subsystem=m.subsystem)[:50]
        ctx["can_change"] = user_can(self.request.user, "M66", "change")
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        if not user_can(request.user, "M66", "change"):
            messages.error(request, "Нет прав.")
            return redirect("platform-ai-policies")
        policy = ai.get_or_create_policy(m.subsystem)
        form = AiPolicyForm(request.POST, instance=policy)
        if form.is_valid():
            form.save()
            messages.success(request, "Политика обновлена.")
        return redirect("platform-ai-policies")


class AiFeedbackCreateView(ModulePermissionMixin, View):
    """#45 — обратная связь по результатам ИИ."""

    module_code = "M47"

    def post(self, request):
        m = _ctx_membership(self)
        try:
            rating = int(request.POST.get("rating", "3"))
        except ValueError:
            rating = 3
        rating = max(1, min(5, rating))
        comment = (request.POST.get("comment") or "").strip()
        prompt_excerpt = (request.POST.get("prompt_excerpt") or "")[:500]
        module_code = (request.POST.get("module_code") or "M47")[:8]
        AiFeedback.objects.create(
            subsystem=m.subsystem,
            user=request.user,
            module_code=module_code,
            rating=rating,
            comment=comment,
            prompt_excerpt=prompt_excerpt,
        )
        from delayu.services import audit

        audit.log_action(
            request.user,
            m.subsystem,
            "ai.feedback",
            "AiFeedback",
            "",
            {"rating": rating, "module_code": module_code},
            request,
        )
        messages.success(request, "Спасибо за отзыв.")
        nxt = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/ai/"
        return redirect(nxt)


class AiHitlListView(ModulePermissionMixin, TemplateView):
    """#42 — очередь проверки результатов ИИ."""

    module_code = "M47"
    template_name = "platform/ai/hitl.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Проверка ИИ (HITL)"
        ctx["ai_tab"] = "hitl"
        status = self.request.GET.get("status", AiHumanReview.Status.PENDING)
        qs = AiHumanReview.objects.filter(subsystem=m.subsystem).select_related("user", "reviewer")
        if status:
            qs = qs.filter(status=status)
        ctx["reviews"] = qs[:50]
        ctx["filter_status"] = status
        ctx["can_review"] = user_can(self.request.user, "M47", "change")
        return ctx


class AiHitlReviewView(ModulePermissionMixin, View):
    module_code = "M47"
    required_action = "change"

    def post(self, request, pk):
        m = _ctx_membership(self)
        review = get_object_or_404(AiHumanReview, pk=pk, subsystem=m.subsystem)
        from delayu.services import audit
        from delayu.services.ai_hitl import approve_review, reject_review

        action = request.POST.get("action")
        comment = (request.POST.get("comment") or "").strip()
        if action == "approve":
            approve_review(review, reviewer=request.user, comment=comment)
            audit.log_action(
                request.user, m.subsystem, "ai.hitl.approve", "AiHumanReview", review.pk, request=request
            )
            messages.success(request, "Результат ИИ утверждён.")
        elif action == "reject":
            reject_review(review, reviewer=request.user, comment=comment)
            audit.log_action(
                request.user, m.subsystem, "ai.hitl.reject", "AiHumanReview", review.pk, request=request
            )
            messages.warning(request, "Результат ИИ отклонён.")
        return redirect("platform-ai-hitl")


class AiHitlCreateView(ModulePermissionMixin, View):
    module_code = "M47"

    def post(self, request):
        m = _ctx_membership(self)
        title = (request.POST.get("title") or "Черновик ИИ")[:255]
        output = request.POST.get("ai_output", "")
        from delayu.services.ai_hitl import create_review

        review = create_review(
            subsystem=m.subsystem,
            user=request.user,
            title=title,
            ai_output=output,
            module_code=request.POST.get("module_code", "M47")[:8],
        )
        from delayu.services import audit

        audit.log_action(
            request.user, m.subsystem, "ai.hitl.create", "AiHumanReview", review.pk, request=request
        )
        messages.info(request, "Отправлено на проверку оператором.")
        nxt = request.POST.get("next") or reverse("platform-ai-hitl")
        return redirect(nxt)


class AiOcrStubView(ModulePermissionMixin, TemplateView):
    module_code = "M51"
    template_name = "platform/ai/ocr.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "OCR документов"
        ctx["ai_tab"] = "tools"
        return ctx
