"""Базовые auth-views без циклических импортов."""
from django.shortcuts import render
from django.views.generic import TemplateView

from web_project import TemplateLayout
from web_project.template_helpers.theme import TemplateHelper


class AuthView(TemplateView):
    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context.update(
            {"layout_path": TemplateHelper.set_layout("layout_blank.html", context)}
        )
        return context


def csrf_failure(request, reason=""):
    """Страница входа вместо стандартной 403 CSRF Django."""
    from delayu.views import LoginView

    view = LoginView()
    view.setup(request)
    ctx = view.get_context_data()
    ctx["csrf_failed"] = True
    ctx["csrf_failure_reason"] = reason
    return render(request, "auth/login.html", ctx, status=403)
