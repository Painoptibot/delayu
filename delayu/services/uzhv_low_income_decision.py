"""Решение по малоимущим и постановка в очередь (ТЗ п. 259–269, 270–275)."""
from __future__ import annotations

from django.utils import timezone

from delayu.models_uzhv import HousingHouseholdMember, HousingQueueCase
from delayu.services.uzhv_case_status import record_case_status_change
from delayu.services.uzhv_low_income import LowIncomeResult, calculate_low_income
from delayu.services.uzhv_queue import recalculate_housing_queue


def sync_applicant_to_household(case: HousingQueueCase) -> HousingHouseholdMember:
    """Добавляет заявителя в состав семьи из карточки гражданина."""
    citizen = case.citizen
    member, created = HousingHouseholdMember.objects.get_or_create(
        case=case,
        relation=HousingHouseholdMember.Relation.APPLICANT,
        defaults={
            "full_name": citizen.full_name,
            "birth_date": citizen.birth_date,
            "snils": citizen.snils,
            "passport_series": citizen.passport_series,
            "passport_number": citizen.passport_number,
            "reg_address": citizen.reg_address,
            "sort_order": 0,
        },
    )
    if not created:
        member.full_name = citizen.full_name
        member.birth_date = citizen.birth_date
        member.snils = citizen.snils
        member.passport_series = citizen.passport_series
        member.passport_number = citizen.passport_number
        member.reg_address = citizen.reg_address
        member.save(
            update_fields=[
                "full_name",
                "birth_date",
                "snils",
                "passport_series",
                "passport_number",
                "reg_address",
            ]
        )
    return member


def apply_low_income_calculation(
    case: HousingQueueCase,
    *,
    subsystem,
    monthly_income,
    household_size,
    property_value,
    user=None,
) -> LowIncomeResult:
    """Расчёт + сохранение полей дела, смена категории при признании малоимущим."""
    result = calculate_low_income(
        subsystem=subsystem,
        monthly_income=monthly_income,
        household_size=household_size,
        property_value=property_value,
        case=case,
    )
    old_category = case.category
    case.household_size = max(int(household_size or 1), 1)
    case.monthly_income = monthly_income
    case.property_value = property_value
    case.per_capita_income = result["per_capita_income"]
    case.low_income_eligible = result["eligible"]
    case.low_income_conclusion = result["conclusion"]
    case.income_verified = True
    case.low_income_calculated_at = timezone.now()
    if result["eligible"] and case.category == HousingQueueCase.Category.GENERAL:
        case.category = HousingQueueCase.Category.LOW_INCOME
    case.save()
    if old_category != case.category:
        record_case_status_change(
            case,
            old_status=case.status,
            new_status=case.status,
            user=user,
            comment=f"Категория: {old_category} → {case.category} (расчёт малоимущих)",
        )
    recalculate_housing_queue(subsystem)
    case.refresh_from_db()
    return result


def reject_low_income_application(case: HousingQueueCase, *, user=None) -> None:
    """Отказ в признании малоимущим — снятие с учёта с основанием."""
    old_status = case.status
    case.low_income_eligible = False
    if not case.low_income_conclusion:
        case.low_income_conclusion = "Отказ в признании малоимущим по результатам расчёта."
    case.status = HousingQueueCase.Status.REJECTED
    case.queue_position = None
    case.save()
    record_case_status_change(
        case,
        old_status=old_status,
        new_status=case.status,
        user=user,
        comment="Отказ в признании малоимущим",
    )
    recalculate_housing_queue(case.subsystem)
