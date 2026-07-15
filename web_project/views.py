from django.views.generic import TemplateView
from web_project import TemplateLayout
from web_project.template_helpers.theme import TemplateHelper


class SystemView(TemplateView):
    template_name = "pages/system/not-found.html"
    status = ""

    def get_context_data(self, **kwargs):
        # A function to init the global layout. It is defined in web_project/__init__.py file
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        # Define the layout for this module
        # _templates/layout/system.html
        context.update(
            {
                "layout_path": TemplateHelper.set_layout("system.html", context),
                "status": self.status,
            }
        )

        return context

    def render_to_response(self, context, **response_kwargs):
        # handler404/403/… передают status=; без этого ответ был HTTP 200,
        # и CommonMiddleware не делал APPEND_SLASH-редирект (например /fuel/novorossiysk).
        if self.status not in ("", None):
            response_kwargs.setdefault("status", int(self.status))
        return super().render_to_response(context, **response_kwargs)
