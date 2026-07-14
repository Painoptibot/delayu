"""Контроль полноты комплекта документов (AI-P0-05 / ИИ-3)."""
from __future__ import annotations

from delayu.models import NSIClassifier, NSIValue
from delayu.models_business import CaseFile, DocumentFile
from delayu.models_uzhv import HousingCaseAttachment, HousingQueueCase


def _nsi_required_rows(subsystem, classifier_code: str, category: str) -> list[tuple[str, str]]:
    """Строки NSI: code «category|doc_kind», name — подпись."""
    clf = NSIClassifier.objects.filter(subsystem=subsystem, code=classifier_code).first()
    if not clf:
        return []
    prefix = f"{category}|"
    rows = []
    for val in NSIValue.objects.filter(classifier=clf, is_active=True).order_by("sort_order", "name"):
        if not str(val.code).startswith(prefix):
            continue
        doc_kind = str(val.code)[len(prefix) :]
        if doc_kind:
            rows.append((doc_kind, val.name))
    return rows


DEFAULT_UZHV_REQUIRED: dict[str, list[tuple[str, str]]] = {
    HousingQueueCase.Category.LOW_INCOME: [
        (HousingCaseAttachment.DocKind.APPLICATION, "Заявление"),
        (HousingCaseAttachment.DocKind.PASSPORT, "Паспорт / удостоверение"),
        (HousingCaseAttachment.DocKind.INCOME, "Справка о доходах"),
        (HousingCaseAttachment.DocKind.PROPERTY, "Сведения об имуществе"),
    ],
    HousingQueueCase.Category.ORPHAN: [
        (HousingCaseAttachment.DocKind.APPLICATION, "Заявление"),
        (HousingCaseAttachment.DocKind.PASSPORT, "Паспорт / удостоверение"),
        (HousingCaseAttachment.DocKind.DECISION, "Решение / заключение"),
    ],
    HousingQueueCase.Category.YOUNG_FAMILY: [
        (HousingCaseAttachment.DocKind.APPLICATION, "Заявление"),
        (HousingCaseAttachment.DocKind.PASSPORT, "Паспорт / удостоверение"),
        (HousingCaseAttachment.DocKind.INCOME, "Справка о доходах"),
    ],
    HousingQueueCase.Category.GENERAL: [
        (HousingCaseAttachment.DocKind.APPLICATION, "Заявление"),
        (HousingCaseAttachment.DocKind.PASSPORT, "Паспорт / удостоверение"),
    ],
}

DEFAULT_CASE_REQUIRED: dict[str, list[tuple[str, str]]] = {
    "default": [
        (DocumentFile.DocType.INCOMING, "Входящий документ"),
        (DocumentFile.DocType.ATTACHMENT, "Вложение"),
    ],
    "correspondence": [
        (DocumentFile.DocType.INCOMING, "Входящее обращение"),
        (DocumentFile.DocType.SCAN, "Скан / копия"),
    ],
}


def required_uzhv_doc_kinds(subsystem, category: str) -> list[tuple[str, str]]:
    nsi_rows = _nsi_required_rows(subsystem, "uzhv_required_doc_kinds", category)
    if nsi_rows:
        return nsi_rows
    return list(DEFAULT_UZHV_REQUIRED.get(category, DEFAULT_UZHV_REQUIRED[HousingQueueCase.Category.GENERAL]))


def required_case_doc_types(subsystem, profile: str = "default") -> list[tuple[str, str]]:
    nsi_rows = _nsi_required_rows(subsystem, "case_required_doc_types", profile)
    if nsi_rows:
        return nsi_rows
    return list(DEFAULT_CASE_REQUIRED.get(profile, DEFAULT_CASE_REQUIRED["default"]))


def housing_case_completeness(case: HousingQueueCase) -> dict:
    """Проверка вложений учётного дела УЖВ по категории и НСИ."""
    required = required_uzhv_doc_kinds(case.subsystem, case.category)
    present = set(case.attachments.values_list("doc_kind", flat=True))
    checks = []
    for doc_kind, label in required:
        checks.append(
            {
                "ok": doc_kind in present,
                "label": label,
                "doc_kind": doc_kind,
                "required": True,
            }
        )
    missing = [c["label"] for c in checks if not c["ok"]]
    total = len(checks)
    done = sum(1 for c in checks if c["ok"])
    return {
        "checks": checks,
        "missing": missing,
        "complete": not missing,
        "score": round(done / total, 2) if total else 1.0,
        "summary": "Комплект полный" if not missing else f"Не хватает: {', '.join(missing)}",
    }


def casefile_completeness(case: CaseFile) -> list[dict]:
    """Расширенная полнота дела M22: регламент + обязательные типы документов."""
    checks = []
    checks.append({"ok": bool(case.assignee_id), "label": "Назначен исполнитель", "required": True})
    checks.append(
        {
            "ok": bool(case.description.strip()),
            "label": "Заполнено описание",
            "required": True,
        }
    )
    checks.append(
        {
            "ok": case.due_date is not None,
            "label": "Указан срок",
            "required": False,
        }
    )

    profile = (case.extra_data or {}).get("doc_profile") or "default"
    required_docs = required_case_doc_types(case.subsystem, profile)
    present = set(
        case.documents.filter(is_current=True).values_list("doc_type", flat=True)
    )
    for doc_type, label in required_docs:
        checks.append(
            {
                "ok": doc_type in present,
                "label": label,
                "doc_type": doc_type,
                "required": True,
            }
        )

    return checks


def casefile_completeness_summary(case: CaseFile) -> dict:
    checks = casefile_completeness(case)
    missing = [c["label"] for c in checks if c.get("required") and not c["ok"]]
    required = [c for c in checks if c.get("required")]
    done = sum(1 for c in required if c["ok"])
    total = len(required) or 1
    return {
        "checks": checks,
        "missing": missing,
        "complete": not missing,
        "score": round(done / total, 2),
        "summary": "Комплект полный" if not missing else f"Не хватает: {', '.join(missing)}",
    }
