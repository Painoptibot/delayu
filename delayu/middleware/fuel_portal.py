"""Поддомен публичного портала «Топливный пропуск»."""
from __future__ import annotations

from django.http import Http404
from django.shortcuts import redirect

from delayu.services.fuel import resolve_fuel_subsystem


class FuelPortalMiddleware:
    """
    Определяет подсистему по поддомену (novorossiysk.delau.tech)
    или по префиксу пути /fuel/<subdomain>/ для локальной разработки.
    """

    PATH_PREFIX = "/fuel/"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.fuel_subsystem = None
        request.fuel_portal_root = ""

        # /fuel/novorossiysk → /fuel/novorossiysk/ (маршрут только со слэшем)
        if (
            request.method in ("GET", "HEAD")
            and request.path.startswith(self.PATH_PREFIX)
            and not request.path.endswith("/")
        ):
            rest = request.path[len(self.PATH_PREFIX) :]
            if rest and "/" not in rest:
                if resolve_fuel_subsystem(path_subdomain=rest):
                    target = f"{request.path}/"
                    if request.META.get("QUERY_STRING"):
                        target = f"{target}?{request.META['QUERY_STRING']}"
                    return redirect(target, permanent=False)

        host = request.get_host()
        sub = resolve_fuel_subsystem(host=host)
        if sub:
            request.fuel_subsystem = sub
            request.fuel_portal_root = ""
        elif request.path.startswith(self.PATH_PREFIX):
            parts = request.path[len(self.PATH_PREFIX) :].split("/", 1)
            slug = parts[0] if parts else ""
            sub = resolve_fuel_subsystem(path_subdomain=slug)
            if sub:
                request.fuel_subsystem = sub
                request.fuel_portal_root = f"{self.PATH_PREFIX}{slug}"
        if request.fuel_subsystem and not request.path.startswith(self.PATH_PREFIX):
            host_sub = resolve_fuel_subsystem(host=host)
            if host_sub and host_sub.pk == request.fuel_subsystem.pk:
                request.urlconf = "delayu.urls_fuel_subdomain"
        return self.get_response(request)


def require_fuel_subsystem(request):
    sub = getattr(request, "fuel_subsystem", None)
    if not sub:
        raise Http404("Портал не найден")
    return sub
