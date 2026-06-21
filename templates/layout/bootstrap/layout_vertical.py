from web_project.template_helpers.theme import TemplateHelper

"""
This is an entry and Bootstrap class for the theme level.
The init() function will be called in web_project/__init__.py
"""


class TemplateBootstrapLayoutVertical:
    def init(context):
        context.update(
            {
                "layout": "vertical",
                "content_navbar": True,
                "is_navbar": True,
                "is_menu": True,
                "is_footer": True,
                "navbar_detached": True,
            }
        )

        # map_context according to updated context values
        TemplateHelper.map_context(context)

        TemplateBootstrapLayoutVertical.init_menu_data(context)

        return context

    def init_menu_data(context):
        if context.get("menu_json"):
            menu_data = context["menu_json"]
        else:
            from django.urls import reverse

            # Не использовать vertical_menu.json (url "index" / "page-2" — только Materio).
            menu_data = {
                "menu": [
                    {
                        "url": "platform-home",
                        "url_href": reverse("platform-home"),
                        "icon": "menu-icon icon-base ri ri-home-smile-line",
                        "name": "Главная",
                        "slug": "platform-home",
                    },
                    {
                        "url": "platform-subsystems",
                        "url_href": reverse("platform-subsystems"),
                        "icon": "menu-icon icon-base ri ri-settings-3-line",
                        "name": "Подсистемы",
                        "slug": "platform-subsystems",
                    },
                    {
                        "url": "platform-help-center",
                        "url_href": reverse("platform-help-center"),
                        "icon": "menu-icon icon-base ri ri-question-line",
                        "name": "Справка",
                        "slug": "platform-help-center",
                    },
                ]
            }
        context.update({"menu_data": menu_data})
