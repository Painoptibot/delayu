"""Кастомные path-конвертеры URL."""
from django.urls import register_converter


class FuelPortalSlugConverter:
    """
    Slug публичного портала — только существующая fuel-подсистема.
    Иначе маршрут не матчится (dashboard, applications и т.д. уходят к оператору).
    """

    regex = r"[a-z0-9][a-z0-9-]*"

    def to_python(self, value):
        from delayu.services.fuel import resolve_fuel_subsystem

        if not resolve_fuel_subsystem(path_subdomain=value):
            raise ValueError
        return value

    def to_url(self, value):
        return value


def register_fuel_converters():
    register_converter(FuelPortalSlugConverter, "fuelportal")
