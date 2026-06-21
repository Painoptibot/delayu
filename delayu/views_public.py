"""Публичные endpoint (без сессии) — бесплатные каналы приёма обращений."""
from __future__ import annotations

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.views.decorators.csrf import csrf_protect
from django.utils.decorators import method_decorator

from delayu.models import Subsystem
from delayu.services.integration_inbound import handle_epgu_appeal


def _public_token_ok(request) -> bool:
    expected = (getattr(settings, "UZHV_PUBLIC_APPEAL_TOKEN", "") or "").strip()
    if not expected:
        return True
    token = (request.headers.get("X-Public-Token") or request.POST.get("token") or "").strip()
    return token == expected


@method_decorator(csrf_protect, name="dispatch")
class UzhvPublicAppealView(View):
    """Публичная форма обращения (аналог ЕПГУ) для подсистемы uzhv."""

    template_name = "platform/public/uzhv_appeal_form.html"

    def get(self, request, subsystem_code: str = "uzhv"):
        subsystem = get_object_or_404(Subsystem, code=subsystem_code, industry_template="uzhv")
        return render(
            request,
            self.template_name,
            {"subsystem": subsystem, "page_title": "Обращение в УЖВ", "form_data": {}},
        )

    def post(self, request, subsystem_code: str = "uzhv"):
        if not _public_token_ok(request):
            return HttpResponse("Неверный токен", status=403)
        subsystem = get_object_or_404(Subsystem, code=subsystem_code, industry_template="uzhv")
        payload = {
            "subject": request.POST.get("subject", ""),
            "body": request.POST.get("body", ""),
            "external_id": request.POST.get("external_id", ""),
            "citizen": {
                "last_name": request.POST.get("last_name", ""),
                "first_name": request.POST.get("first_name", ""),
                "middle_name": request.POST.get("middle_name", ""),
                "phone": request.POST.get("phone", ""),
                "email": request.POST.get("email", ""),
            },
        }
        try:
            result = handle_epgu_appeal(subsystem, payload)
        except Exception as exc:
            return render(
                request,
                self.template_name,
                {
                    "subsystem": subsystem,
                    "error": str(exc)[:300],
                    "form_data": request.POST,
                },
                status=400,
            )
        return render(
            request,
            "platform/public/uzhv_appeal_success.html",
            {"subsystem": subsystem, "result": result},
        )
