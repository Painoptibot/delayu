"""M46 — аудиоархив; M62 — транскрибация."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, TemplateView

from delayu.forms_audio import AudioUploadForm
from delayu.mixins import ModulePermissionMixin
from delayu.models import AudioArchiveItem
from delayu.services.access import user_can
from delayu.services.audio import audio_metrics, demo_transcribe, filter_audio
from delayu.views_platform import _ctx_membership


class AudioArchiveListView(ModulePermissionMixin, TemplateView):
    module_code = "M46"
    template_name = "platform/archive/audio_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Аудиоархив"
        ctx["items"] = filter_audio(m.subsystem, self.request.GET)[:50]
        ctx["metrics"] = audio_metrics(m.subsystem)
        ctx["search_q"] = self.request.GET.get("q", "")
        ctx["filter_source"] = self.request.GET.get("source_type", "")
        ctx["source_choices"] = AudioArchiveItem.SourceType.choices
        ctx["can_create"] = user_can(self.request.user, "M46", "create")
        return ctx


class AudioUploadView(ModulePermissionMixin, TemplateView):
    module_code = "M46"
    required_action = "create"
    template_name = "platform/archive/audio_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Загрузка записи"
        ctx["form"] = kwargs.get("form") or AudioUploadForm(
            subsystem=_ctx_membership(self).subsystem
        )
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = AudioUploadForm(request.POST, request.FILES, subsystem=m.subsystem)
        if form.is_valid():
            item = form.save(commit=False)
            item.subsystem = m.subsystem
            item.created_by = request.user
            item.recorded_at = form.cleaned_data.get("recorded_at") or timezone.now()
            item.save()
            messages.success(request, "Запись добавлена в архив.")
            return redirect("platform-audio-detail", pk=item.pk)
        return self.render_to_response(self.get_context_data(form=form))


class AudioDetailView(ModulePermissionMixin, DetailView):
    module_code = "M46"
    model = AudioArchiveItem
    template_name = "platform/archive/audio_detail.html"
    context_object_name = "item"

    def get_queryset(self):
        return AudioArchiveItem.objects.filter(
            subsystem=_ctx_membership(self).subsystem
        ).select_related("case", "created_by")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_change"] = user_can(self.request.user, "M46", "change")
        return ctx


class AudioModalView(ModulePermissionMixin, View):
    module_code = "M46"

    def get(self, request, pk):
        item = get_object_or_404(
            AudioArchiveItem, pk=pk, subsystem=_ctx_membership(self).subsystem
        )
        return render(request, "platform/archive/_audio_modal.html", {"item": item})


class AudioTranscribeView(ModulePermissionMixin, View):
    module_code = "M62"
    required_action = "change"

    def post(self, request, pk):
        item = get_object_or_404(
            AudioArchiveItem, pk=pk, subsystem=_ctx_membership(self).subsystem
        )
        demo_transcribe(item)
        from delayu.services import ai

        ai._log(
            item.subsystem,
            request.user,
            "M62",
            f"transcribe:{item.pk}",
            item.transcript[:200],
        )
        messages.success(request, "Транскрипт сформирован (демо).")
        return redirect("platform-audio-detail", pk=pk)


class AudioArchiveView(AudioArchiveListView):
    """Совместимость URL platform-audio."""

    pass
