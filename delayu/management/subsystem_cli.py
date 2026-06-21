"""Общие хелперы для management-команд с --subsystem."""
from __future__ import annotations

from django.core.management.base import OutputWrapper


def filter_subsystems(qs, code: str, *, stdout: OutputWrapper, style) -> list | None:
    """Отфильтровать подсистемы; при неизвестном code — сообщение и None."""
    from delayu.models import Subsystem

    code = (code or "").strip()
    if not code:
        return list(qs)
    filtered = qs.filter(code=code)
    if filtered.exists():
        return list(filtered)
    available = list(Subsystem.objects.order_by("code").values_list("code", flat=True))
    if available:
        hint = ", ".join(available)
    else:
        hint = "нет — выполните: manage.bat seed_demo"
    stdout.write(style.ERROR(f'Подсистема «{code}» не найдена. Доступные коды: {hint}'))
    stdout.write(
        style.WARNING(
            "Подсказка: демо-контур создаётся командой seed_demo (код подсистемы обычно pilot, не core)."
        )
    )
    return None
