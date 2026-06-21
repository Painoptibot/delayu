"""Маршруты списков УЖВ для QR-кодов (?open=)."""
from __future__ import annotations

UZHV_QR_ENTITIES: dict[str, tuple[str, str]] = {
    "citizens": ("HousingCitizen", "/uzhv/citizens/"),
    "appeals": ("HousingAppeal", "/uzhv/appeals/"),
    "cases": ("HousingQueueCase", "/uzhv/cases/"),
    "buildings": ("MunicipalBuilding", "/uzhv/fund/"),
    "contracts": ("HousingContract", "/uzhv/contracts/"),
    "inspections": ("HousingInspection", "/uzhv/inspections/"),
    "prescriptions": ("HousingPrescription", "/uzhv/prescriptions/"),
    "court-cases": ("HousingCourtCase", "/uzhv/court-cases/"),
    "interagency": ("HousingInteragencyRequest", "/uzhv/interagency/"),
    "admin-protocols": ("HousingAdminProtocol", "/uzhv/admin-protocols/"),
    "young-families": ("HousingQueueCase", "/uzhv/young-families/"),
    "orphans": ("HousingQueueCase", "/uzhv/orphans/"),
}


def model_for_entity(entity: str):
    from delayu import models_uzhv

    name = UZHV_QR_ENTITIES[entity][0]
    return getattr(models_uzhv, name)
