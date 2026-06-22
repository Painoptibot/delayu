"""Lookup-поля: выбор записи реестра и автоподстановка (#11)."""
from delayu.models import RegistryRecord, RegistryType


def registry_choices(subsystem, registry_code: str, *, label_field: str = "name", limit: int = 200):
    rt = RegistryType.objects.filter(
        subsystem=subsystem, code=registry_code, is_active=True
    ).first()
    if not rt:
        return []
    out = []
    for rec in RegistryRecord.objects.filter(registry_type=rt).order_by("-pk")[:limit]:
        data = rec.data or {}
        label = data.get(label_field) or data.get("name") or rec.external_id or str(rec.pk)
        out.append({"id": rec.pk, "label": str(label)[:200]})
    return out


def registry_record_payload(subsystem, registry_code: str, record_id: int) -> dict | None:
    rt = RegistryType.objects.filter(
        subsystem=subsystem, code=registry_code, is_active=True
    ).first()
    if not rt:
        return None
    rec = RegistryRecord.objects.filter(registry_type=rt, pk=record_id).first()
    if not rec:
        return None
    data = dict(rec.data or {})
    data["_id"] = rec.pk
    data["_external_id"] = rec.external_id
    return data
