"""M23 — универсальные реестры: схема полей, валидация, импорт."""
import json

from delayu.models import RegistryRecord, RegistryType


def parse_field_schema(raw: str) -> list:
    data = json.loads(raw or "[]")
    if not isinstance(data, list):
        raise ValueError("Ожидается JSON-массив полей")
    out = []
    for item in data:
        if not isinstance(item, dict) or not item.get("key"):
            raise ValueError("Каждое поле должно содержать key")
        out.append(
            {
                "key": str(item["key"]).strip(),
                "label": str(item.get("label") or item["key"]).strip(),
                "required": bool(item.get("required")),
            }
        )
    return out


def validate_record_data(registry_type: RegistryType, data: dict) -> dict:
    from delayu.services.form_schemas import resolve_registry_schema, validate_schema_data

    schema = resolve_registry_schema(registry_type)
    if schema:
        return validate_schema_data(schema, data)
    schema = registry_type.field_schema or []
    cleaned = {}
    errors = {}
    for field in schema:
        key = field["key"]
        val = data.get(key, "")
        if isinstance(val, str):
            val = val.strip()
        if field.get("required") and not val:
            errors[key] = "Обязательное поле"
        cleaned[key] = val
    return cleaned, errors


def import_records(registry_type, organization, user, rows: list) -> tuple[int, list]:
    """Импорт списка dict; возвращает (создано, ошибки)."""
    created = 0
    errors = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"Строка {i + 1}: не объект")
            continue
        cleaned, errs = validate_record_data(registry_type, row)
        if errs:
            errors.append(f"Строка {i + 1}: {errs}")
            continue
        RegistryRecord.objects.create(
            registry_type=registry_type,
            organization=organization,
            external_id=str(row.get("external_id", "") or "")[:64],
            data=cleaned,
            created_by=user,
        )
        created += 1
    return created, errors
