"""Загрузка и рендер текущего ТЗ для модального окна."""
import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.utils.html import escape
from django.utils.safestring import mark_safe

TZ_FILENAME = "TZ-PLATFORM-2.2.md"


def tz_file_path() -> Path:
    return Path(settings.BASE_DIR) / "docs" / TZ_FILENAME


def load_tz_markdown() -> str:
    path = tz_file_path()
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _render_md(text: str) -> str:
    try:
        import markdown

        return markdown.markdown(text, extensions=["tables", "fenced_code", "nl2br"])
    except ImportError:
        return f"<pre style='white-space:pre-wrap'>{escape(text[:50000])}</pre>"


@lru_cache(maxsize=4)
def _render_tz_html_cached(mtime: float) -> str:
    path = tz_file_path()
    if not path.is_file():
        return "<p>Файл <code>docs/TZ-PLATFORM-2.2.md</code> не найден.</p>"
    text = path.read_text(encoding="utf-8")
    return _render_md(text)


def render_tz_html() -> str:
    path = tz_file_path()
    if not path.is_file():
        return "<p>Файл <code>docs/TZ-PLATFORM-2.2.md</code> не найден.</p>"
    return _render_tz_html_cached(path.stat().st_mtime)


def tz_context() -> dict:
    text = load_tz_markdown()
    version = "2.2"
    m = re.search(r"\*\*Версия документа\*\*\s*\|\s*([^|]+)", text)
    if m:
        version = m.group(1).strip()
    return {
        "tz_html": mark_safe(render_tz_html()),
        "tz_title": "Техническое задание — ДелаЮ (платформа)",
        "tz_meta": f"Файл: docs/{TZ_FILENAME} · версия: {version}",
    }
