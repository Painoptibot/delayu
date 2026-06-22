"""Публичная презентация платформы (/welcome/)."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django.views import View
from django.views.generic import RedirectView

PRESENTATION_ROOT = Path(settings.BASE_DIR) / "docs" / "presentation_delau"


def _safe_path(relative: str) -> Path:
    root = PRESENTATION_ROOT.resolve()
    full = (PRESENTATION_ROOT / relative).resolve()
    if not str(full).startswith(str(root)):
        raise Http404
    return full


def _html_with_base(path: Path) -> HttpResponse:
    if not path.is_file():
        raise Http404
    html = path.read_text(encoding="utf-8")
    if "<base " not in html:
        html = html.replace("<head>", '<head>\n  <base href="/presentation/">', 1)
    return HttpResponse(html, content_type="text/html; charset=utf-8")


class WelcomeView(View):
    """Интерактивная презентация ДелаЮ."""

    def get(self, request):
        return _html_with_base(PRESENTATION_ROOT / "index.html")


class WelcomeRedirectView(RedirectView):
    permanent = True
    pattern_name = "platform-welcome"


class PresentationAssetView(View):
    """Статика презентации: /presentation/assets/..."""

    def get(self, request, asset_path: str):
        path = _safe_path(asset_path)
        if path.suffix.lower() in {".html", ".htm"}:
            return _html_with_base(path)
        if not path.is_file():
            raise Http404
        return FileResponse(path.open("rb"))
