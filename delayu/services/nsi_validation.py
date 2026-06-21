"""Валидация значений НСИ (#5)."""
from delayu.models import NSIValue


def value_exists(subsystem, classifier_code: str, value_code: str) -> bool:
    if not value_code:
        return True
    return NSIValue.objects.filter(
        classifier__subsystem=subsystem,
        classifier__code=classifier_code,
        classifier__is_active=True,
        code=str(value_code),
        is_active=True,
    ).exists()


def validate_choice(subsystem, classifier_code: str, value_code: str, field_label: str):
    if value_code and not value_exists(subsystem, classifier_code, value_code):
        return {field_label: f"Значение «{value_code}» отсутствует в справочнике {classifier_code}"}
    return {}
