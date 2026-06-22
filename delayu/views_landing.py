"""Публичный лендинг платформы ДелаЮ."""

from django.views.generic import TemplateView

from delayu.views_auth import AuthView


class LandingView(AuthView):
    """Маркетинговая страница /landing/ — без авторизации."""

    template_name = "landing/index.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["has_customizer"] = False
        return ctx
