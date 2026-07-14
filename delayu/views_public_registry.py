"""Публичная документация для реестра Минцифры (без авторизации)."""

from django.views import View
from django.views.generic import TemplateView

from delayu.views_auth import AuthView


class PublicRegistryDocsView(AuthView):
    """Главная: функциональные характеристики + установка/эксплуатация."""

    template_name = "public/registry/index.html"

    def get_context_data(self, **kwargs):
        from delayu.services.registry_platform import build_public_registry_hub

        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Документация «ДелаЮ» — реестр Минцифры"
        ctx["hub"] = build_public_registry_hub()
        ctx["has_customizer"] = False
        return ctx


class PublicRegistryPassportView(AuthView):
    template_name = "public/registry/passport.html"

    def get_context_data(self, **kwargs):
        from delayu.services.registry_platform import build_product_passport, resolve_registry_subsystem

        ctx = super().get_context_data(**kwargs)
        sub = resolve_registry_subsystem()
        ctx["page_title"] = "Паспорт продукта"
        ctx["passport"] = build_product_passport(sub)
        ctx["has_customizer"] = False
        return ctx


class PublicRegistryDemoView(AuthView):
    template_name = "public/registry/demo.html"

    def get_context_data(self, **kwargs):
        from delayu.services.registry_platform import build_registry_demo_guide, resolve_registry_subsystem

        ctx = super().get_context_data(**kwargs)
        sub = resolve_registry_subsystem()
        ctx["page_title"] = "Демо-сценарий для экспертизы"
        ctx["guide"] = build_registry_demo_guide(sub)
        ctx["has_customizer"] = False
        return ctx


class PublicRegistryApplicationView(AuthView):
    template_name = "public/registry/application.html"

    def get_context_data(self, **kwargs):
        from delayu.services.registry_platform import build_registry_application, resolve_registry_subsystem

        ctx = super().get_context_data(**kwargs)
        sub = resolve_registry_subsystem()
        ctx["page_title"] = "Тексты заявления в реестр"
        ctx["application"] = build_registry_application(sub)
        ctx["has_customizer"] = False
        return ctx


class PublicRegistryAiView(AuthView):
    template_name = "public/registry/ai.html"

    def get_context_data(self, **kwargs):
        from delayu.services.registry_platform import build_ai_module_doc, resolve_registry_subsystem

        ctx = super().get_context_data(**kwargs)
        sub = resolve_registry_subsystem()
        ctx["page_title"] = "Модуль интеллектуальной обработки данных"
        ctx["doc"] = build_ai_module_doc(sub)
        ctx["has_customizer"] = False
        return ctx


class PublicRegistryTariffsView(AuthView):
    template_name = "public/registry/tariffs.html"

    def get_context_data(self, **kwargs):
        from delayu.services.registry_platform import build_tariff_policy

        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Тарифная политика"
        ctx["tariff"] = build_tariff_policy()
        ctx["has_customizer"] = False
        return ctx


class PublicRegistrySourceCodeView(AuthView):
    template_name = "public/registry/source_code.html"

    def get_context_data(self, **kwargs):
        from delayu.services.registry_platform import build_source_code_infra_doc

        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Хранение исходного кода и сборка"
        ctx["doc"] = build_source_code_infra_doc()
        ctx["has_customizer"] = False
        return ctx


class PublicRegistryExportView(View):
    """PDF-экспорт без входа (для экспертизы реестра)."""

    def get(self, request, kind: str):
        from delayu.services.registry_platform import (
            export_ai_module_pdf,
            export_demo_guide_pdf,
            export_passport_pdf,
            export_registry_application_pdf,
            export_source_code_infra_pdf,
            export_tariff_policy_pdf,
            resolve_registry_subsystem,
        )

        sub = resolve_registry_subsystem()
        exporters = {
            "passport": export_passport_pdf,
            "demo": export_demo_guide_pdf,
            "application": export_registry_application_pdf,
            "ai": export_ai_module_pdf,
            "tariffs": lambda _sub: export_tariff_policy_pdf(),
            "source-code": lambda _sub: export_source_code_infra_pdf(),
        }
        exporter = exporters.get(kind)
        if not exporter:
            from django.http import Http404

            raise Http404
        return exporter(sub)
