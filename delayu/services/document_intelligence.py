"""OCR + NER: интelligentное распознавание документов «ДелаЮ»."""
from __future__ import annotations

import io

from django.core.files.uploadedfile import UploadedFile

from delayu.services import ocr, uzhv_ner
from delayu.services.ai_gateway import invoke


def recognize_upload(file_obj: UploadedFile | object, *, filename: str = "") -> dict:
    """Полный результат распознавания без записи в БД."""
    ocr_result = ocr.extract_text_from_upload(file_obj, filename=filename)
    text = ocr_result.get("text") or ""
    fields = uzhv_ner.extract_application_fields(text)
    return {
        "text_preview": text[:4000],
        "text_length": len(text),
        "engine": ocr_result.get("engine", ""),
        "pages": ocr_result.get("pages", 0),
        "warnings": ocr_result.get("warnings") or [],
        "fields": fields,
        "field_count": len(fields),
    }


def recognize_with_gateway(subsystem, user, file_obj, *, filename: str = "", module_code: str = "M51") -> dict:
    """Распознавание с записью в AiRequestLog."""
    raw = b""
    if hasattr(file_obj, "read"):
        raw = file_obj.read()
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
    buf = io.BytesIO(raw) if raw else io.BytesIO()
    result = recognize_upload(buf, filename=filename)

    def handler():
        return f"fields={result['field_count']} engine={result['engine']}"

    invoke(
        subsystem,
        user,
        module_code,
        f"ocr:{filename}"[:500],
        handler,
        meta={"engine": result["engine"], "field_count": result["field_count"]},
    )
    return result


def apply_uzhv_fields(case, citizen, payload: dict, *, user) -> list[str]:
    """
    Применяет подтверждённые пользователем поля (HITL).
    payload: {key: value} только отмеченные поля.
    Возвращает список human-readable изменений.
    """
    from datetime import date

    changes: list[str] = []
    citizen_fields = {
        "last_name",
        "first_name",
        "middle_name",
        "snils",
        "passport_series",
        "passport_number",
        "reg_address",
        "phone",
        "email",
    }
    case_fields = {"household_size", "monthly_income", "low_income_application_at"}

    c_updates: list[str] = []
    for key in citizen_fields:
        if key not in payload:
            continue
        val = str(payload[key]).strip()
        if not val:
            continue
        old = getattr(citizen, key, "")
        if str(old) == val:
            continue
        setattr(citizen, key, val)
        c_updates.append(key)
        changes.append(f"Гражданин.{key}: «{old}» → «{val}»")

    if c_updates:
        citizen.save(update_fields=[*c_updates, "updated_at"])

    case_updates: list[str] = []
    for key in case_fields:
        if key not in payload:
            continue
        raw = str(payload[key]).strip()
        if not raw:
            continue
        if key == "household_size":
            val = int(raw)
            if case.household_size != val:
                case.household_size = val
                case_updates.append(key)
                changes.append(f"Дело.household_size → {val}")
        elif key == "monthly_income":
            from decimal import Decimal

            val = Decimal(raw.replace(",", "."))
            if case.monthly_income != val:
                case.monthly_income = val
                case_updates.append(key)
                changes.append(f"Дело.monthly_income → {val}")
        elif key == "low_income_application_at":
            val = date.fromisoformat(raw)
            if case.low_income_application_at != val:
                from delayu.services.uzhv_low_income import compute_low_income_review_due

                case.low_income_application_at = val
                case.low_income_review_due_at = compute_low_income_review_due(val, case.subsystem)
                case_updates.extend(
                    ["low_income_application_at", "low_income_review_due_at"]
                )
                changes.append(f"Дело.дата заявления → {val.isoformat()}")

    if case_updates:
        case_updates.append("updated_at")
        case.save(update_fields=list(dict.fromkeys(case_updates)))

    if changes:
        from delayu.services import audit

        audit.log_action(
            user,
            case.subsystem,
            "ai.ocr.apply",
            "HousingQueueCase",
            case.pk,
            {"changes": changes, "citizen_id": citizen.pk},
        )
    return changes
