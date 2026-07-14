"""Извлечение реквизитов заявления УЖВ из текста (NER + правила)."""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from delayu.services.ai import extract_entities

FIO_PATTERN = re.compile(
    r"(?:ф\.?\s*и\.?\s*о\.?|заявитель|гражданин)\s*[:\-]?\s*"
    r"([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,2})",
    re.IGNORECASE,
)
FIO_LINE = re.compile(r"^([А-ЯЁ][а-яё]+)\s+([А-ЯЁ][а-яё]+)(?:\s+([А-ЯЁ][а-яё]+))?", re.MULTILINE)
SNILS_RE = re.compile(r"\b(\d{3}[-\s]?\d{3}[-\s]?\d{3}[-\s]?\d{2})\b")
PASSPORT_RE = re.compile(
    r"(?:паспорт|серия|документ)\s*[:\s]*(\d{2}\s?\d{2})[\s,]*(\d{6})",
    re.IGNORECASE,
)
PASSPORT_SIMPLE = re.compile(r"\b(\d{4})\s+(\d{6})\b")
ADDRESS_RE = re.compile(
    r"(?:адрес(?:\s+регистрации)?|прожива(?:ет|ющ)|место\s+жительства)\s*[:\-]\s*(.+?)(?:\n|$)",
    re.IGNORECASE,
)
INCOME_RE = re.compile(
    r"(?:доход|заработок|среднемесячный\s+доход)\s*[:\s]*([\d\s]+(?:[.,]\d{2})?)",
    re.IGNORECASE,
)
HOUSEHOLD_RE = re.compile(
    r"(?:состав\s+семьи|число\s+членов|количество\s+членов)\s*[:\s]*(\d{1,2})",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{2,4})\b")
APPLICATION_DATE_RE = re.compile(
    r"(?:дата\s+заявления|заявление\s+от)\s*[:\s]*(\d{1,2}[./]\d{1,2}[./]\d{2,4})",
    re.IGNORECASE,
)


def _field(key: str, label: str, value: str, confidence: float, source: str = "") -> dict:
    return {
        "key": key,
        "label": label,
        "value": value,
        "confidence": round(min(1.0, max(0.0, confidence)), 2),
        "source": source[:200],
    }


def _parse_date(raw: str) -> str | None:
    m = DATE_RE.search(raw)
    if not m:
        return None
    d, mo, y = m.groups()
    year = int(y)
    if year < 100:
        year += 2000 if year < 50 else 1900
    try:
        return datetime(year, int(mo), int(d)).date().isoformat()
    except ValueError:
        return None


def _parse_money(raw: str) -> str | None:
    cleaned = raw.replace(" ", "").replace(",", ".")
    try:
        return str(Decimal(cleaned).quantize(Decimal("0.01")))
    except InvalidOperation:
        return None


def extract_application_fields(text: str) -> list[dict]:
    """Реквизиты заявления / учётного дела из распознанного текста."""
    if not text or not text.strip():
        return []

    fields: list[dict] = []
    t = text.replace("\r", "\n")

    # ФИО
    fio_match = FIO_PATTERN.search(t)
    if fio_match:
        full = fio_match.group(1).strip()
        parts = full.split()
        if len(parts) >= 2:
            fields.append(_field("last_name", "Фамилия", parts[0], 0.88, fio_match.group(0)))
            fields.append(_field("first_name", "Имя", parts[1], 0.86, fio_match.group(0)))
            if len(parts) >= 3:
                fields.append(_field("middle_name", "Отчество", parts[2], 0.84, fio_match.group(0)))
    elif (line_match := FIO_LINE.search(t)):
        fields.append(_field("last_name", "Фамилия", line_match.group(1), 0.72, line_match.group(0)))
        fields.append(_field("first_name", "Имя", line_match.group(2), 0.70, line_match.group(0)))
        if line_match.group(3):
            fields.append(_field("middle_name", "Отчество", line_match.group(3), 0.68, line_match.group(0)))

    # СНИЛС
    if snils := SNILS_RE.search(t):
        norm = re.sub(r"[\s\-]", "", snils.group(1))
        if len(norm) == 11:
            formatted = f"{norm[0:3]}-{norm[3:6]}-{norm[6:9]} {norm[9:11]}"
            fields.append(_field("snils", "СНИЛС", formatted, 0.92, snils.group(0)))

    # Паспорт
    passport = PASSPORT_RE.search(t) or PASSPORT_SIMPLE.search(t)
    if passport:
        series = passport.group(1).replace(" ", "")
        number = passport.group(2)
        fields.append(_field("passport_series", "Серия паспорта", series, 0.85, passport.group(0)))
        fields.append(_field("passport_number", "Номер паспорта", number, 0.85, passport.group(0)))

    # Адрес
    if addr := ADDRESS_RE.search(t):
        val = addr.group(1).strip(" .;")
        if len(val) > 5:
            fields.append(_field("reg_address", "Адрес регистрации", val[:500], 0.80, addr.group(0)))

    # Контакты
    entities = extract_entities(t)
    if entities.get("phones"):
        fields.append(_field("phone", "Телефон", entities["phones"][0].strip(), 0.75, entities["phones"][0]))
    if entities.get("emails"):
        fields.append(_field("email", "E-mail", entities["emails"][0], 0.75, entities["emails"][0]))

    # Доход
    if inc := INCOME_RE.search(t):
        money = _parse_money(inc.group(1))
        if money:
            fields.append(_field("monthly_income", "Среднемесячный доход, ₽", money, 0.78, inc.group(0)))

    # Состав семьи
    if hh := HOUSEHOLD_RE.search(t):
        fields.append(_field("household_size", "Число членов семьи", hh.group(1), 0.77, hh.group(0)))

    # Дата заявления
    app_raw = APPLICATION_DATE_RE.search(t)
    if app_raw:
        iso = _parse_date(app_raw.group(1))
    else:
        iso = _parse_date(t[:500])
    if iso:
        fields.append(_field("low_income_application_at", "Дата заявления", iso, 0.74, app_raw.group(0) if app_raw else iso))

    # Дедуп по key — оставляем с max confidence
    best: dict[str, dict] = {}
    for item in fields:
        prev = best.get(item["key"])
        if not prev or item["confidence"] > prev["confidence"]:
            best[item["key"]] = item
    return list(best.values())


def fields_to_prefill_dict(fields: list[dict]) -> dict[str, str]:
    return {f["key"]: f["value"] for f in fields if f.get("value")}
