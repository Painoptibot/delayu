"""Справочники НСИ для подсистемы УЖВ."""
from __future__ import annotations

from delayu.models import NSIClassifier, NSIValue


def nsi_value_choices(subsystem, classifier_code: str) -> list[tuple[str, str]]:
    clf = NSIClassifier.objects.filter(subsystem=subsystem, code=classifier_code).first()
    if not clf:
        return []
    return [
        (v.name, v.name)
        for v in NSIValue.objects.filter(classifier=clf, is_active=True).order_by(
            "sort_order", "name"
        )
    ]


def get_nsi_int(subsystem, classifier_code: str, default: int) -> int:
    clf = NSIClassifier.objects.filter(subsystem=subsystem, code=classifier_code).first()
    if not clf:
        return default
    row = NSIValue.objects.filter(classifier=clf, is_active=True).order_by("-sort_order").first()
    if not row:
        return default
    try:
        return int(str(row.code).strip())
    except (TypeError, ValueError):
        return default


INSPECTION_SUBJECT_DEFAULTS = [
    ("01", "Содержание общего имущества МКД", 1),
    ("02", "Правила пользования жилыми помещениями", 2),
    ("03", "Содержание и ремонт жилого фонда", 3),
    ("04", "Благоустройство прилегающей территории", 4),
    ("05", "Деятельность управляющей организации", 5),
    ("06", "Содержание лифтового оборудования", 6),
    ("07", "Санитарное состояние МКД", 7),
    ("08", "Противопожарное состояние МКД", 8),
]


def seed_uzhv_nsi_classifiers(subsystem) -> None:
    """Дополнительные классификаторы УЖВ (вызывается из seed_uzhv)."""
    review_days, _ = NSIClassifier.objects.update_or_create(
        subsystem=subsystem,
        code="uzhv_low_income_review_days",
        defaults={
            "name": "Срок рассмотрения заявления малоимущих, дней",
            "description": "По умолчанию 30",
        },
    )
    NSIValue.objects.update_or_create(
        classifier=review_days,
        code="30",
        defaults={"name": "30 календарных дней", "sort_order": 1},
    )

    subjects, _ = NSIClassifier.objects.update_or_create(
        subsystem=subsystem,
        code="uzhv_inspection_subjects",
        defaults={
            "name": "Предметы проверок (жилконтроль)",
            "description": "ТЗ п. 1.5.4.2.7.1",
        },
    )
    for code, name, order in INSPECTION_SUBJECT_DEFAULTS:
        NSIValue.objects.update_or_create(
            classifier=subjects,
            code=code,
            defaults={"name": name, "sort_order": order},
        )
