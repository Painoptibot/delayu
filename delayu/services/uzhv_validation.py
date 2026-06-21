"""PY-03 — валидация СНИЛС и паспортных полей перед импортом."""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field


@dataclass
class ValidationRowError:
    row: int
    field: str
    value: str
    message: str


@dataclass
class ValidationReport:
    total_rows: int = 0
    valid_rows: int = 0
    errors: list[ValidationRowError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def normalize_snils(raw: str) -> str:
    return re.sub(r"\D", "", raw or "")


def validate_snils(raw: str) -> tuple[bool, str]:
    digits = normalize_snils(raw)
    if not digits:
        return True, ""
    if len(digits) != 11:
        return False, "СНИЛС должен содержать 11 цифр"
    if digits[:9] == "000000000":
        return False, "Некорректный номер СНИЛС"
    nums = [int(ch) for ch in digits[:9]]
    checksum = 0
    for i, n in enumerate(nums):
        checksum += n * (9 - i)
    if checksum < 100:
        control = checksum
    elif checksum in (100, 101):
        control = 0
    else:
        control = checksum % 101
        if control == 100:
            control = 0
    expected = int(digits[9:11])
    if control != expected:
        return False, f"Неверная контрольная сумма СНИЛС (ожидалось {control:02d})"
    return True, ""


def validate_passport_series(raw: str) -> tuple[bool, str]:
    val = re.sub(r"\s", "", raw or "")
    if not val:
        return True, ""
    if not re.fullmatch(r"\d{4}", val):
        return False, "Серия паспорта: 4 цифры"
    return True, ""


def validate_passport_number(raw: str) -> tuple[bool, str]:
    val = re.sub(r"\s", "", raw or "")
    if not val:
        return True, ""
    if not re.fullmatch(r"\d{6}", val):
        return False, "Номер паспорта: 6 цифр"
    return True, ""


def _detect_delimiter(sample: str) -> str:
    if sample.count(";") >= sample.count(","):
        return ";"
    return ","


def validate_citizens_csv(content: str, *, encoding: str = "utf-8") -> ValidationReport:
    """Проверка CSV граждан: колонки snils, passport_series, passport_number (гибкий заголовок)."""
    report = ValidationReport()
    text = content.lstrip("\ufeff")
    if not text.strip():
        report.errors.append(ValidationRowError(0, "", "", "Файл пуст"))
        return report

    delimiter = _detect_delimiter(text.splitlines()[0])
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        report.errors.append(ValidationRowError(0, "", "", "Нет строки заголовка"))
        return report

    fields = {h.strip().lower(): h for h in reader.fieldnames if h}

    def col(*names: str) -> str | None:
        for n in names:
            if n in fields:
                return fields[n]
        return None

    snils_col = col("snils", "снилс")
    series_col = col("passport_series", "серия", "passport series")
    number_col = col("passport_number", "номер", "passport number")

    for row_num, row in enumerate(reader, start=2):
        report.total_rows += 1
        row_ok = True
        if snils_col:
            ok, msg = validate_snils(row.get(snils_col, ""))
            if not ok:
                report.errors.append(
                    ValidationRowError(row_num, "snils", row.get(snils_col, ""), msg)
                )
                row_ok = False
        if series_col:
            ok, msg = validate_passport_series(row.get(series_col, ""))
            if not ok:
                report.errors.append(
                    ValidationRowError(row_num, "passport_series", row.get(series_col, ""), msg)
                )
                row_ok = False
        if number_col:
            ok, msg = validate_passport_number(row.get(number_col, ""))
            if not ok:
                report.errors.append(
                    ValidationRowError(row_num, "passport_number", row.get(number_col, ""), msg)
                )
                row_ok = False
        if row_ok:
            report.valid_rows += 1

    return report


def validation_report_csv(report: ValidationReport) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["row", "field", "value", "message"])
    for err in report.errors:
        w.writerow([err.row, err.field, err.value, err.message])
    w.writerow([])
    w.writerow(["total_rows", report.total_rows])
    w.writerow(["valid_rows", report.valid_rows])
    w.writerow(["error_count", len(report.errors)])
    return buf.getvalue()
