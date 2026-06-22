"""Проверка наличия статических файлов в шаблонах."""

from django import template
from django.contrib.staticfiles import finders

register = template.Library()


@register.simple_tag
def static_exists(static_path: str) -> bool:
    return finders.find(static_path) is not None
