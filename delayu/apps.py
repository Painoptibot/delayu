from django.apps import AppConfig


class DelayuConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "delayu"
    verbose_name = "Платформа ДелаЮ"

    def ready(self):
        from delayu.converters import register_fuel_converters

        register_fuel_converters()
