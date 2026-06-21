"""Подстановка значений НСИ в ChoiceField форм."""
from __future__ import annotations

from delayu.models import NSIValue


def choices_for(subsystem, classifier_code: str, fallback=(), *, cast=None):
    """Список (value, label) из НСИ или fallback из модели."""
    if not subsystem:
        return list(fallback)
    qs = NSIValue.objects.filter(
        classifier__subsystem=subsystem,
        classifier__code=classifier_code,
        classifier__is_active=True,
        is_active=True,
    ).order_by("sort_order", "name")
    if not qs.exists():
        return list(fallback)
    out = []
    for row in qs:
        val = row.code
        if cast is int:
            try:
                val = int(row.code)
            except ValueError:
                pass
        out.append((val, row.name))
    return out


def apply_field(form, field_name: str, subsystem, classifier_code: str, fallback=(), *, cast=None):
    """Заменить choices поля формы значениями справочника."""
    if field_name not in form.fields:
        return
    form.fields[field_name].choices = choices_for(
        subsystem, classifier_code, fallback, cast=cast
    )


def sync_classifiers_for_subsystem(subsystem):
    """Создать/обновить все справочники из каталога."""
    from delayu.data.nsi_classifiers import NSI_CATALOG
    from delayu.models import NSIClassifier

    for code, name, description, values in NSI_CATALOG:
        clf, _ = NSIClassifier.objects.update_or_create(
            subsystem=subsystem,
            code=code,
            defaults={"name": name, "description": description, "is_active": True},
        )
        for sort, (vcode, vname) in enumerate(values, start=1):
            from delayu.models import NSIValue

            NSIValue.objects.update_or_create(
                classifier=clf,
                code=vcode,
                defaults={"name": vname, "sort_order": sort, "is_active": True},
            )
