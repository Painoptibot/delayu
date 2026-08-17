# -*- coding: utf-8 -*-
"""Веб-витрина карты ЮФО для Android WebView."""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404
from django.shortcuts import render
from django.views import View
from django.views.generic import TemplateView


def ufo_public_context():
    return {
        "page_brand": "Топливный пропуск · ЮФО",
        "api_base": "/fuel/api/ufo",
        "app_url": "/fuel/ufo/app/",
        "support_url": "/fuel/ufo/support/",
        "privacy_url": "/fuel/ufo/legal/privacy/",
        "rules_url": "/fuel/ufo/legal/rules/",
        "android_url": "/fuel/ufo/android/",
        "apk_url": "/fuel/ufo/android/fuel-ufo.apk",
        "fuel_support_email": settings.FUEL_SUPPORT_EMAIL,
    }


class FuelUfoPageMixin:
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(ufo_public_context())
        return ctx


class FuelUfoMobileMapView(FuelUfoPageMixin, TemplateView):
    template_name = "fuel/ufo/mobile_map.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["yandex_maps_api_key"] = getattr(settings, "YANDEX_MAPS_API_KEY", "") or ""
        return ctx


class FuelUfoLegalPrivacyView(FuelUfoPageMixin, TemplateView):
    template_name = "fuel/ufo/legal_privacy.html"


class FuelUfoLegalRulesView(FuelUfoPageMixin, TemplateView):
    template_name = "fuel/ufo/legal_rules.html"


class FuelUfoSupportView(FuelUfoPageMixin, TemplateView):
    template_name = "fuel/ufo/support.html"


class FuelUfoAndroidInstallView(FuelUfoPageMixin, TemplateView):
    template_name = "fuel/ufo/android.html"


class FuelUfoApkDownloadView(View):
    """Signed sideload APK for tablets/phones (not the store listing)."""

    def get(self, request):
        path = Path(__file__).resolve().parent / "static" / "fuel" / "ufo" / "fuel-ufo.apk"
        if not path.is_file():
            raise Http404("APK не найден")
        response = FileResponse(
            path.open("rb"),
            as_attachment=True,
            filename="Топливный пропуск.apk",
            content_type="application/vnd.android.package-archive",
        )
        response["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response["Content-Disposition"] = (
            "attachment; filename=\"Toplivnyy-propusk.apk\"; "
            "filename*=UTF-8''%D0%A2%D0%BE%D0%BF%D0%BB%D0%B8%D0%B2%D0%BD%D1%8B%D0%B9%20%D0%BF%D1%80%D0%BE%D0%BF%D1%83%D1%81%D0%BA.apk"
        )
        return response


class FuelUfoServiceWorkerView(View):
    def get(self, request):
        response = render(request, "fuel/ufo/sw.js", {}, content_type="application/javascript")
        response["Service-Worker-Allowed"] = "/fuel/ufo/"
        response["Cache-Control"] = "no-cache"
        return response
