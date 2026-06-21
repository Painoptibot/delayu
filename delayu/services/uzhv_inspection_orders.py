"""Предписания на проведение проверок (ТЗ п. 322)."""
from __future__ import annotations

from delayu.models_uzhv import HousingInspection, HousingInspectionOrder


def spawn_inspection_from_order(order: HousingInspectionOrder) -> HousingInspection:
    from delayu.services.uzhv import next_inspection_number

    if order.inspection_id:
        return order.inspection
    inspection = HousingInspection.objects.create(
        subsystem=order.subsystem,
        plan=order.plan,
        inspection_number=next_inspection_number(order.subsystem),
        inspection_type=HousingInspection.InspectionType.UNPLANNED
        if order.plan_id
        else HousingInspection.InspectionType.PLANNED,
        object_type=order.object_type,
        building=order.building,
        counterparty_name=order.addressee if not order.building_id else "",
        check_subject=order.check_subject,
        planned_date=order.conduct_by,
        status=HousingInspection.Status.PLANNED,
    )
    order.inspection = inspection
    order.status = HousingInspectionOrder.Status.SCHEDULED
    order.save(update_fields=["inspection", "status", "updated_at"])
    return inspection


def complete_inspection_order_for_inspection(inspection: HousingInspection) -> bool:
    """Закрывает предписание на проверку, если проверка завершена."""
    if inspection.status != HousingInspection.Status.COMPLETED:
        return False
    try:
        order = inspection.conduct_order
    except HousingInspectionOrder.DoesNotExist:
        return False
    if order.status == HousingInspectionOrder.Status.COMPLETED:
        return False
    order.status = HousingInspectionOrder.Status.COMPLETED
    order.save(update_fields=["status", "updated_at"])
    return True
