"""PY-04 — миграция из CSV по mapping.json / mapping.yaml."""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from delayu.models_uzhv import HousingCitizen, HousingQueueCase


@dataclass
class MigrationResult:
    created: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def load_mapping(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore

            return yaml.safe_load(text) or {}
        except ImportError as exc:
            raise RuntimeError("Для YAML установите PyYAML или используйте mapping.json") from exc
    return json.loads(text)


def _parse_date(val: str):
    val = (val or "").strip()
    if not val:
        return timezone.now().date()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(val[:10], fmt).date()
        except ValueError:
            continue
    return timezone.now().date()


@transaction.atomic
def migrate_from_mapping(subsystem, mapping: dict, source_path: Path) -> MigrationResult:
    """
    mapping.json:
    {
      "entity": "citizen" | "case",
      "delimiter": ";",
      "columns": { "last_name": "Фамилия", ... },
      "defaults": { "category": "general" }
    }
    """
    result = MigrationResult()
    entity = (mapping.get("entity") or "citizen").lower()
    delimiter = mapping.get("delimiter") or ";"
    col_map: dict[str, str] = mapping.get("columns") or {}
    defaults = mapping.get("defaults") or {}

    if not col_map:
        result.errors.append("В mapping не задан блок columns")
        return result

    raw = source_path.read_bytes()
    content = None
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            content = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if content is None:
        result.errors.append("Не удалось прочитать кодировку исходника")
        return result

    reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")), delimiter=delimiter)
    if not reader.fieldnames:
        result.errors.append("Пустой CSV")
        return result
    header = {h.strip(): h for h in reader.fieldnames if h}

    def cell(row, field_key: str) -> str:
        src = col_map.get(field_key)
        if not src:
            return str(defaults.get(field_key, ""))
        key = header.get(src.strip(), src)
        return (row.get(key) or "").strip()

    for row_num, row in enumerate(reader, start=2):
        if entity == "citizen":
            last = cell(row, "last_name")
            first = cell(row, "first_name")
            if not last:
                result.skipped += 1
                continue
            snils = cell(row, "snils")
            citizen, created = HousingCitizen.objects.get_or_create(
                subsystem=subsystem,
                last_name=last[:128],
                first_name=first[:128] or "—",
                defaults={
                    "middle_name": cell(row, "middle_name")[:128],
                    "snils": snils[:14],
                    "reg_address": cell(row, "reg_address")[:500],
                    "phone": cell(row, "phone")[:32],
                },
            )
            if created:
                result.created += 1
            else:
                result.skipped += 1

        elif entity == "case":
            case_number = cell(row, "case_number")
            last = cell(row, "last_name")
            first = cell(row, "first_name")
            if not case_number or not last:
                result.errors.append(f"Строка {row_num}: нужны case_number и last_name")
                continue
            citizen, _ = HousingCitizen.objects.get_or_create(
                subsystem=subsystem,
                last_name=last[:128],
                first_name=first[:128] or "—",
                defaults={"middle_name": cell(row, "middle_name")[:128]},
            )
            category = cell(row, "category") or defaults.get("category", HousingQueueCase.Category.GENERAL)
            status = cell(row, "status") or defaults.get("status", HousingQueueCase.Status.REGISTERED)
            _, created = HousingQueueCase.objects.update_or_create(
                subsystem=subsystem,
                case_number=case_number[:64],
                defaults={
                    "citizen": citizen,
                    "category": category,
                    "status": status,
                    "registered_at": _parse_date(cell(row, "registered_at")),
                    "notes": cell(row, "notes"),
                },
            )
            if created:
                result.created += 1
            else:
                result.skipped += 1
        else:
            result.errors.append(f"Неизвестный entity: {entity}")
            break

    return result
