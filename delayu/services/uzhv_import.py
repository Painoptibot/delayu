"""Импорт договоров из xlsx (шаблон Горжилхоз)."""
from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from delayu.models_uzhv import (
    HousingCitizen,
    HousingContract,
    MunicipalBuilding,
    MunicipalPremise,
)


@dataclass
class ImportResult:
    created: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def _read_xlsx_rows(uploaded_file) -> list[list[str]]:
    """Читает первый лист xlsx в список строк (stdlib)."""
    with zipfile.ZipFile(uploaded_file) as z:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            for si in root.findall(".//m:si", ns):
                texts = [t.text or "" for t in si.findall(".//m:t", ns)]
                shared.append("".join(texts))
        sheet_name = "xl/worksheets/sheet1.xml"
        if sheet_name not in z.namelist():
            return []
        sheet = ET.fromstring(z.read(sheet_name))
        ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

        def col_index(cell_ref: str) -> int:
            letters = re.match(r"([A-Z]+)", cell_ref or "")
            if not letters:
                return 0
            idx = 0
            for ch in letters.group(1):
                idx = idx * 26 + (ord(ch) - ord("A") + 1)
            return idx - 1

        by_row: dict[int, dict[int, str]] = {}
        for row_el in sheet.findall(".//m:sheetData/m:row", ns):
            r_idx = int(row_el.get("r", "0") or 0)
            for c in row_el.findall("m:c", ns):
                ref = c.get("r", "")
                t = c.get("t")
                v = c.find("m:v", ns)
                val = v.text if v is not None else ""
                if t == "s" and val.isdigit():
                    val = shared[int(val)]
                by_row.setdefault(r_idx, {})[col_index(ref)] = str(val).strip()

        if not by_row:
            return []
        max_col = max(max(cols.keys()) for cols in by_row.values())
        out = []
        for r in sorted(by_row.keys()):
            cols = by_row[r]
            out.append([cols.get(i, "") for i in range(max_col + 1)])
        return out


def _parse_date(val: str):
    val = (val or "").strip()
    if not val:
        return timezone.now().date()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(val[:10], fmt).date()
        except ValueError:
            continue
    return timezone.now().date()


def _map_contract_type(label: str) -> str:
    low = (label or "").lower()
    if "специализ" in low:
        return HousingContract.ContractType.SPECIAL
    if "коммер" in low:
        return HousingContract.ContractType.COMMERCIAL
    if "приват" in low:
        return HousingContract.ContractType.PRIVATIZATION
    return HousingContract.ContractType.SOCIAL


def _find_header_row(rows: list[list[str]]) -> int | None:
    for i, row in enumerate(rows):
        joined = " ".join(row).lower()
        if "номер договора" in joined and ("фамилия" in joined or "наниматель" in joined):
            return i
    return None


def _column_map(header: list[str]) -> dict[str, int]:
    m = {}
    for i, cell in enumerate(header):
        low = cell.lower()
        if "тип" in low and "договор" in low:
            m["type"] = i
        elif "номер" in low and "договор" in low:
            m["number"] = i
        elif "дата" in low and "заключ" in low:
            m["date"] = i
        elif "дата" in low and ("окончан" in low or "действ" in low):
            m["valid_until"] = i
        elif cell.strip().lower() == "фамилия":
            m["last_name"] = i
        elif cell.strip().lower() == "имя":
            m["first_name"] = i
        elif "отчество" in low:
            m["middle_name"] = i
        elif "снилс" in low:
            m["snils"] = i
        elif "адрес" in low:
            m["address"] = i
        elif "квартира" in low or ("номер" in low and "помещ" in low):
            m["premise_number"] = i
        elif "площад" in low:
            m["area_sqm"] = i
        elif "комнат" in low:
            m["rooms"] = i
    return m


def _get_cell(row: list[str], idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    return (row[idx] or "").strip()


def _ensure_premise(
    subsystem,
    address: str,
    *,
    number: str | None = None,
    area_sqm: str | None = None,
    rooms: str | None = None,
) -> MunicipalPremise | None:
    address = (address or "").strip()
    if not address and not number:
        return None
    if not number:
        m = re.search(r"кв\.?\s*(\S+)", address, re.I)
        number = m.group(1) if m else "б/н"
    number = number[:32]
    building_addr = address.split(", кв")[0].split(", кв.")[0].strip() if address else ""
    if not building_addr:
        building_addr = address[:500] or "Адрес не указан"
    building, _ = MunicipalBuilding.objects.get_or_create(
        subsystem=subsystem,
        address=building_addr[:500],
        defaults={},
    )
    defaults = {"status": MunicipalPremise.Status.OCCUPIED}
    if area_sqm:
        try:
            defaults["area_sqm"] = area_sqm.replace(",", ".")
        except (ValueError, TypeError):
            pass
    if rooms:
        try:
            defaults["rooms"] = int(float(str(rooms).replace(",", ".")))
        except (ValueError, TypeError):
            pass
    premise, created = MunicipalPremise.objects.get_or_create(
        building=building,
        number=number,
        defaults=defaults,
    )
    if not created:
        updated = []
        if area_sqm and not premise.area_sqm:
            try:
                premise.area_sqm = area_sqm.replace(",", ".")
                updated.append("area_sqm")
            except (ValueError, TypeError):
                pass
        if rooms and not premise.rooms:
            try:
                premise.rooms = int(float(str(rooms).replace(",", ".")))
                updated.append("rooms")
            except (ValueError, TypeError):
                pass
        if premise.status == MunicipalPremise.Status.FREE:
            premise.status = MunicipalPremise.Status.OCCUPIED
            updated.append("status")
        if updated:
            premise.save(update_fields=updated)
    return premise


@transaction.atomic
def import_contracts_from_rows(subsystem, rows: list[list[str]]) -> ImportResult:
    result = ImportResult()
    header_idx = _find_header_row(rows)
    if header_idx is None:
        result.errors.append("Не найдена строка заголовка (ожидаются колонки «Номер договора», «Фамилия»)")
        return result

    cols = _column_map(rows[header_idx])
    if "number" not in cols:
        result.errors.append("Колонка «Номер договора» не найдена")
        return result

    for row in rows[header_idx + 1 :]:
        number = _get_cell(row, cols.get("number"))
        if not number or number in ("1", "2", "3", "4", "5", "6"):
            continue
        last = _get_cell(row, cols.get("last_name"))
        if not last:
            result.skipped += 1
            continue
        first = _get_cell(row, cols.get("first_name"))
        middle = _get_cell(row, cols.get("middle_name"))
        snils = _get_cell(row, cols.get("snils"))
        addr = _get_cell(row, cols.get("address"))
        citizen_defaults = {
            "middle_name": middle,
            "reg_address": addr,
        }
        if snils:
            citizen_defaults["snils"] = snils[:14]
        citizen, _ = HousingCitizen.objects.get_or_create(
            subsystem=subsystem,
            last_name=last,
            first_name=first or "—",
            defaults=citizen_defaults,
        )
        if snils and not citizen.snils:
            citizen.snils = snils[:14]
            citizen.save(update_fields=["snils"])
        premise = _ensure_premise(
            subsystem,
            addr,
            number=_get_cell(row, cols.get("premise_number")) or None,
            area_sqm=_get_cell(row, cols.get("area_sqm")) or None,
            rooms=_get_cell(row, cols.get("rooms")) or None,
        )
        ctype = _map_contract_type(_get_cell(row, cols.get("type")))
        signed = _parse_date(_get_cell(row, cols.get("date")))
        valid_until_raw = _get_cell(row, cols.get("valid_until"))
        valid_until = _parse_date(valid_until_raw) if valid_until_raw else None
        obj, created = HousingContract.objects.update_or_create(
            subsystem=subsystem,
            contract_number=number[:64],
            defaults={
                "contract_type": ctype,
                "citizen": citizen,
                "premise": premise,
                "signed_at": signed,
                "valid_until": valid_until,
                "is_active": True,
            },
        )
        if created:
            result.created += 1
        else:
            result.skipped += 1
    return result


def import_contracts_xlsx(subsystem, uploaded_file) -> ImportResult:
    try:
        rows = _read_xlsx_rows(uploaded_file)
    except zipfile.BadZipFile:
        r = ImportResult()
        r.errors.append("Файл не является корректным xlsx")
        return r
    if not rows:
        r = ImportResult()
        r.errors.append("Лист пуст")
        return r
    return import_contracts_from_rows(subsystem, rows)
