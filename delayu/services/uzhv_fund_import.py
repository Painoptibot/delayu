"""PY-01 — импорт жилфонда и договоров из CSV/XLSX."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from django.db import transaction

from delayu.models_uzhv import MunicipalBuilding, MunicipalPremise
from delayu.services.uzhv_import import ImportResult, import_contracts_xlsx


@dataclass
class FundImportResult:
    buildings_created: int = 0
    buildings_updated: int = 0
    premises_created: int = 0
    premises_updated: int = 0
    errors: list[str] = field(default_factory=list)


def _map_premise_status(raw: str) -> str:
    low = (raw or "").lower()
    if "занят" in low or "occupied" in low:
        return MunicipalPremise.Status.OCCUPIED
    if "резерв" in low or "reserved" in low:
        return MunicipalPremise.Status.RESERVED
    return MunicipalPremise.Status.FREE


def _map_building_condition(raw: str) -> str:
    low = (raw or "").lower()
    if "авар" in low or "emergency" in low:
        return MunicipalBuilding.Condition.EMERGENCY
    if "рассел" in low or "renovation" in low:
        return MunicipalBuilding.Condition.RENOVATION
    return MunicipalBuilding.Condition.OK


def _detect_delimiter(line: str) -> str:
    return ";" if line.count(";") >= line.count(",") else ","


@transaction.atomic
def import_fund_csv(subsystem, content: str) -> FundImportResult:
    """
    CSV: address; premise_number; area_sqm; rooms; status; condition; in_resettlement
    Заголовок обязателен (address + premise_number или number).
    """
    result = FundImportResult()
    text = content.lstrip("\ufeff")
    if not text.strip():
        result.errors.append("Файл пуст")
        return result

    lines = text.splitlines()
    delimiter = _detect_delimiter(lines[0])
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        result.errors.append("Нет заголовка")
        return result

    norm = {h.strip().lower(): h for h in reader.fieldnames if h}

    def get(row, *keys: str) -> str:
        for k in keys:
            if k in norm:
                return (row.get(norm[k]) or "").strip()
        return ""

    for row_num, row in enumerate(reader, start=2):
        address = get(row, "address", "адрес", "building_address")
        number = get(row, "premise_number", "number", "номер", "квартира")
        if not address:
            result.errors.append(f"Строка {row_num}: пустой адрес")
            continue
        if not number:
            number = "б/н"

        condition_raw = get(row, "condition", "состояние")
        in_prog = get(row, "in_resettlement", "resettlement", "расселение").lower() in (
            "1",
            "true",
            "yes",
            "да",
        )
        cadastral = get(
            row,
            "cadastral_number",
            "cadastre",
            "кадастровый",
            "кадастровый_номер",
            "gis_id",
        )
        floors_raw = get(row, "floors", "этажность", "этажей")
        year_raw = get(row, "year_built", "год", "год_постройки")
        uk_name = get(row, "uk_name", "управляющая", "ук", "management_company")
        lat_raw = get(row, "latitude", "lat", "широта")
        lon_raw = get(row, "longitude", "lon", "долгота")
        gis_note = get(row, "gis_object_id", "object_id", "id_гис")

        b_defaults = {
            "condition": _map_building_condition(condition_raw),
            "in_resettlement_program": in_prog,
        }
        if cadastral:
            b_defaults["cadastral_number"] = cadastral[:64]
        for field, raw in (("floors", floors_raw), ("year_built", year_raw)):
            if raw:
                try:
                    b_defaults[field] = int(float(raw.replace(",", ".")))
                except (ValueError, TypeError):
                    pass
        for field, raw in (("latitude", lat_raw), ("longitude", lon_raw)):
            if raw:
                try:
                    b_defaults[field] = raw.replace(",", ".")
                except (ValueError, TypeError):
                    pass
        notes_parts = []
        if uk_name:
            notes_parts.append(f"УК: {uk_name[:200]}")
        if gis_note:
            notes_parts.append(f"ГИС ЖКХ ID: {gis_note[:80]}")
        if notes_parts:
            b_defaults["notes"] = "; ".join(notes_parts)[:2000]

        building, b_created = MunicipalBuilding.objects.get_or_create(
            subsystem=subsystem,
            address=address[:500],
            defaults=b_defaults,
        )
        if b_created:
            result.buildings_created += 1
        else:
            updated = False
            if condition_raw and building.condition != _map_building_condition(condition_raw):
                building.condition = _map_building_condition(condition_raw)
                updated = True
            if in_prog and not building.in_resettlement_program:
                building.in_resettlement_program = True
                updated = True
            for key in (
                "cadastral_number",
                "floors",
                "year_built",
                "latitude",
                "longitude",
                "notes",
            ):
                if key in b_defaults and getattr(building, key) != b_defaults.get(key):
                    setattr(building, key, b_defaults[key])
                    updated = True
            if updated:
                building.save()
                result.buildings_updated += 1

        area = get(row, "area_sqm", "area", "площадь")
        rooms = get(row, "rooms", "комнат")
        status_raw = get(row, "status", "статус")
        defaults = {"status": _map_premise_status(status_raw)}
        if area:
            try:
                defaults["area_sqm"] = area.replace(",", ".")
            except (ValueError, TypeError):
                pass
        if rooms:
            try:
                defaults["rooms"] = int(float(rooms.replace(",", ".")))
            except (ValueError, TypeError):
                pass

        premise, p_created = MunicipalPremise.objects.get_or_create(
            building=building,
            number=number[:32],
            defaults=defaults,
        )
        if p_created:
            result.premises_created += 1
        else:
            changed = False
            for key, val in defaults.items():
                if getattr(premise, key) != val:
                    setattr(premise, key, val)
                    changed = True
            if changed:
                premise.save()
                result.premises_updated += 1

    return result


def import_registry_file(subsystem, path, *, kind: str = "auto") -> FundImportResult | ImportResult:
    """Универсальный импорт: fund (csv), contracts (xlsx)."""
    name = str(path).lower()
    with open(path, "rb") as fh:
        if kind == "contracts" or (kind == "auto" and name.endswith((".xlsx", ".xlsm"))):
            return import_contracts_xlsx(subsystem, fh)
        if kind == "fund" or (kind == "auto" and name.endswith(".csv")):
            raw = fh.read()
            for enc in ("utf-8-sig", "utf-8", "cp1251"):
                try:
                    return import_fund_csv(subsystem, raw.decode(enc))
                except UnicodeDecodeError:
                    continue
            r = FundImportResult()
            r.errors.append("Не удалось определить кодировку CSV (UTF-8 / cp1251)")
            return r
    r = FundImportResult()
    r.errors.append(f"Неизвестный тип файла: {path}")
    return r
