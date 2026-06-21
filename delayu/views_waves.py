"""Представления волн 1–4: поиск, онбординг, privacy API."""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from delayu.menu import get_active_membership
from delayu.mixins import PlatformLayoutMixin
from delayu.services.access import get_membership_or_403
from delayu.services.object_registry import global_search
from delayu.services.onboarding import (
    build_steps,
    dismiss_onboarding,
    is_dismissed,
    mark_step,
)
from delayu.services.privacy import privacy_mode_active, set_privacy_mode, user_may_view_pii


class GlobalSearchView(LoginRequiredMixin, View):
    """Глобальный поиск Cmd+K (#33)."""

    def get(self, request):
        m = get_active_membership(request.user)
        if not m:
            return JsonResponse({"results": []})
        q = request.GET.get("q", "")
        raw = global_search(m.subsystem, q, user=request.user)
        out = []
        for r in raw:
            url_name = r["url_name"]
            if r.get("open_on_list"):
                url = reverse(url_name) + f"?open={r['id']}"
            elif r["type"] == "document":
                url = reverse(url_name) + f"?open={r['id']}"
            else:
                url = reverse(url_name, kwargs={"pk": r["id"]})
            out.append(
                {
                    "type": r["type"],
                    "type_label": r["type_label"],
                    "id": r["id"],
                    "title": r["title"],
                    "url": url,
                }
            )
        return JsonResponse({"results": out})


class PrivacyModeToggleView(LoginRequiredMixin, View):
    """GET/POST — режим скрытия ПДн (#11)."""

    def get(self, request):
        return JsonResponse(
            {
                "privacy_mode": privacy_mode_active(request),
                "allow_pii": user_may_view_pii(request.user, request),
            }
        )

    def post(self, request):
        enabled = request.POST.get("enabled") == "1"
        set_privacy_mode(request, enabled)
        return JsonResponse(
            {
                "ok": True,
                "privacy_mode": enabled,
                "allow_pii": user_may_view_pii(request.user, request),
            }
        )


class OnboardingChecklistView(LoginRequiredMixin, PlatformLayoutMixin, TemplateView):
    """Интерактивный онбординг (#50)."""

    template_name = "platform/onboarding_checklist.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = get_active_membership(self.request.user)
        steps = build_steps(self.request.user, m)
        done_count = sum(1 for s in steps if s["done"])
        ctx["page_title"] = "Первые шаги"
        ctx["onboarding_steps"] = steps
        ctx["onboarding_done"] = done_count == len(steps) if steps else False
        ctx["onboarding_progress"] = int(100 * done_count / len(steps)) if steps else 0
        ctx["onboarding_dismissed"] = is_dismissed(self.request.user)
        ctx["current_step"] = next((s for s in steps if not s["done"]), steps[-1] if steps else None)
        return ctx

    def post(self, request):
        action = request.POST.get("action", "")
        if action == "dismiss":
            dismiss_onboarding(request.user)
            messages.info(request, "Онбординг скрыт. Вернуться можно из меню «Первые шаги».")
            return redirect("platform-home")
        step_id = request.POST.get("step_id", "")
        if step_id:
            mark_step(request.user, step_id)
            messages.success(request, "Шаг отмечен выполненным.")
        return redirect("platform-onboarding-checklist")
