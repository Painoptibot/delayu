"""Критерии молодых семей (ТЗ п. 279–284, Законы КК № 2704/2710-КЗ — упрощённая модель)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.utils import timezone

from delayu.models_uzhv import YoungFamilyRecord


MAX_SPOUSE_AGE = 35
MIN_MARRIAGE_YEARS_FOR_JSK = 0  # брак действующий


@dataclass
class YoungFamilyCriteriaResult:
    meets: bool
    notes: str
    applicant_age: int | None
    spouse_age: int | None


def _age_on(birth: date | None, on: date) -> int | None:
    if not birth:
        return None
    years = on.year - birth.year
    if (on.month, on.day) < (birth.month, birth.day):
        years -= 1
    return years


def check_young_family_criteria(record: YoungFamilyRecord) -> YoungFamilyCriteriaResult:
    """
    Упрощённые критерии прототипа:
    - оба супруга не старше 35 лет (если даты рождения указаны);
    - наличие даты брака;
    - для ЖСК — указаны ФИО супруга;
    - для экономкласса — не менее 1 ребёнка или беременность (учитываем children_count).
    """
    case = record.case
    citizen = case.citizen
    today = timezone.now().date()
    issues: list[str] = []
    ok: list[str] = []

    app_age = _age_on(citizen.birth_date, today)
    spouse_age = _age_on(record.spouse_birth_date, today)

    if app_age is None:
        issues.append("Не указана дата рождения заявителя")
    elif app_age > MAX_SPOUSE_AGE:
        issues.append(f"Возраст заявителя {app_age} лет превышает {MAX_SPOUSE_AGE}")
    else:
        ok.append(f"Возраст заявителя {app_age} лет")

    if not record.spouse_last_name and not record.spouse_first_name:
        issues.append("Не указаны данные супруга(и)")
    elif spouse_age is None:
        issues.append("Не указана дата рождения супруга(и)")
    elif spouse_age > MAX_SPOUSE_AGE:
        issues.append(f"Возраст супруга(и) {spouse_age} лет превышает {MAX_SPOUSE_AGE}")
    else:
        ok.append(f"Возраст супруга(и) {spouse_age} лет")

    if not record.marriage_date:
        issues.append("Не указана дата брака")
    elif record.marriage_date > today:
        issues.append("Дата брака в будущем")
    else:
        ok.append(f"Брак зарегистрирован {record.marriage_date:%d.%m.%Y}")

    if record.program == YoungFamilyRecord.Program.ECONOMY and record.children_count < 1:
        issues.append("Для программы экономкласса требуется наличие детей (children_count ≥ 1)")

    if record.program == YoungFamilyRecord.Program.JSK:
        ok.append("Программа: члены ЖСК (2704-КЗ)")
    else:
        ok.append("Программа: жильё экономкласса (2710-КЗ)")

    meets = not issues
    parts = []
    if ok:
        parts.append("Соответствует: " + "; ".join(ok))
    if issues:
        parts.append("Не соответствует: " + "; ".join(issues))
    return YoungFamilyCriteriaResult(
        meets=meets,
        notes=" ".join(parts),
        applicant_age=app_age,
        spouse_age=spouse_age,
    )
