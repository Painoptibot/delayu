"""Расчёт признания малоимущими (ТЗ п. 259–269, Закон КК № 1890-КЗ — упрощённая модель)."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import TypedDict

from delayu.models import NSIClassifier, NSIValue
from delayu.services.uzhv_nsi import get_nsi_int


class LowIncomeResult(TypedDict):
    per_capita_income: Decimal
    subsistence_minimum: Decimal
    property_limit: Decimal
    income_ok: bool
    property_ok: bool
    eligible: bool
    conclusion: str


def _decimal(val) -> Decimal:
    if val is None or val == "":
        return Decimal("0")
    return Decimal(str(val))


def get_subsistence_minimum(subsystem) -> Decimal:
    """Прожиточный минимум на душу (НСИ подсистемы или значение по умолчанию)."""
    default = Decimal("16089")  # ориентир КК, настраивается в НСИ
    clf = NSIClassifier.objects.filter(subsystem=subsystem, code="uzhv_subsistence_minimum").first()
    if not clf:
        return default
    row = NSIValue.objects.filter(classifier=clf, is_active=True).order_by("-sort_order", "code").first()
    if not row:
        return default
    try:
        return _decimal(row.code.replace(",", "."))
    except Exception:
        return default


def property_limit_per_capita(subsystem) -> Decimal:
    default = Decimal("250000")
    clf = NSIClassifier.objects.filter(subsystem=subsystem, code="uzhv_property_limit").first()
    if not clf:
        return default
    row = NSIValue.objects.filter(classifier=clf, is_active=True).first()
    if not row:
        return default
    try:
        return _decimal(row.code.replace(",", "."))
    except Exception:
        return default


def get_low_income_review_days(subsystem) -> int:
    return get_nsi_int(subsystem, "uzhv_low_income_review_days", 30)


def compute_low_income_review_due(application_date: date, subsystem) -> date:
    return application_date + timedelta(days=get_low_income_review_days(subsystem))


def calculate_low_income(
    *,
    subsystem,
    monthly_income,
    household_size,
    property_value,
    case=None,
) -> LowIncomeResult:
    """
    Упрощённый расчёт для прототипа:
    - среднедушевой доход = суммарный месячный доход / число членов семьи;
    - доход ниже прожиточного минимума;
    - стоимость имущества не превышает лимит на семью.
    """
    size = max(int(household_size or 1), 1)
    income = _decimal(monthly_income)
    if case is not None:
        members = list(case.household_members.all())
        if members:
            size = max(len(members), 1)
            member_income = sum(_decimal(m.monthly_income) for m in members)
            if member_income > 0:
                income = member_income
    prop = _decimal(property_value)
    pm = get_subsistence_minimum(subsystem)
    prop_cap = property_limit_per_capita(subsystem) * size
    per_capita = (income / size).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    income_ok = per_capita < pm
    property_ok = prop <= prop_cap
    eligible = income_ok and property_ok

    if eligible:
        conclusion = (
            f"Заключение: гражданин (семья из {size} чел.) может быть признан малоимущим. "
            f"Среднедушевой доход {per_capita} ₽/мес. ниже ПМ {pm} ₽. "
            f"Стоимость имущества {prop} ₽ не превышает предельную {prop_cap} ₽."
        )
    elif not income_ok and not property_ok:
        conclusion = (
            f"Отказ: среднедушевой доход {per_capita} ₽/мес. не ниже ПМ {pm} ₽; "
            f"имущество {prop} ₽ превышает лимит {prop_cap} ₽."
        )
    elif not income_ok:
        conclusion = (
            f"Отказ: среднедушевой доход {per_capita} ₽/мес. не ниже прожиточного минимума {pm} ₽."
        )
    else:
        conclusion = (
            f"Отказ: стоимость имущества {prop} ₽ превышает предельную {prop_cap} ₽ для семьи из {size} чел."
        )

    return {
        "per_capita_income": per_capita,
        "subsistence_minimum": pm,
        "property_limit": prop_cap,
        "income_ok": income_ok,
        "property_ok": property_ok,
        "eligible": eligible,
        "conclusion": conclusion,
    }
