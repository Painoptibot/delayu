import csv
import io
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from delayu.models_invest import (
    InvestImportBatch,
    InvestImportRow,
    InvestProject,
    InvestSite,
)

PROJECT_FIELDS = ("name", "stage", "investment_amount")
SITE_FIELDS = ("name", "status")


def _decode_file(file):
    raw = file.read()
    if hasattr(file, "seek"):
        file.seek(0)
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _parse_decimal(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value).replace(",", ".").strip())
    except (InvalidOperation, ValueError):
        return None


def _normalize_row(raw):
    return {k.strip().lower(): (v.strip() if v else "") for k, v in raw.items() if k}


def _project_diff(existing, data):
    changes = {}
    for field in PROJECT_FIELDS:
        incoming = data.get(field, "")
        if field == "investment_amount":
            new_val = _parse_decimal(incoming)
            old_val = getattr(existing, field)
            if new_val is not None and new_val != old_val:
                changes[field] = str(new_val)
        elif incoming and getattr(existing, field) != incoming:
            changes[field] = incoming
    return changes


def _site_diff(existing, data):
    changes = {}
    for field in SITE_FIELDS:
        incoming = data.get(field, "")
        if incoming and getattr(existing, field) != incoming:
            changes[field] = incoming
    return changes


def _site_data(data):
    status = data.get("status") or data.get("stage") or ""
    return {
        "cadastral_number": data.get("cadastral_number", ""),
        "name": data.get("name", ""),
        "status": status,
    }


def _is_site_row(data):
    return bool(data.get("cadastral_number"))


@transaction.atomic
def parse_mo_file(file, *, subsystem, organization) -> InvestImportBatch:
    text = _decode_file(file)
    reader = csv.DictReader(io.StringIO(text))
    batch = InvestImportBatch.objects.create(
        subsystem=subsystem,
        organization=organization,
        source_file=file,
        status=InvestImportBatch.Status.REVIEWING,
    )

    imported_codes = set()
    imported_cadastral = set()
    row_number = 0

    for raw in reader:
        data = _normalize_row(raw)
        if not any(data.values()):
            continue

        if _is_site_row(data):
            site_data = _site_data(data)
            cadastral = site_data["cadastral_number"]
            imported_cadastral.add(cadastral)
            existing = InvestSite.objects.filter(
                subsystem=subsystem, cadastral_number=cadastral,
            ).first()
            if existing is None:
                row_number += 1
                InvestImportRow.objects.create(
                    batch=batch,
                    row_number=row_number,
                    action=InvestImportRow.Action.NEW_SITE,
                    payload={k: v for k, v in site_data.items() if v},
                )
            else:
                changes = _site_diff(existing, site_data)
                if not changes:
                    continue
                row_number += 1
                InvestImportRow.objects.create(
                    batch=batch,
                    row_number=row_number,
                    action=InvestImportRow.Action.CHANGED_SITE,
                    payload={"changes": changes, **site_data},
                    target_site=existing,
                )
        else:
            code = data.get("code", "")
            if not code:
                continue
            imported_codes.add(code)
            existing = InvestProject.objects.filter(subsystem=subsystem, code=code).first()
            payload = {k: data.get(k, "") for k in ("code", "name", "stage", "investment_amount") if data.get(k)}
            if existing is None:
                row_number += 1
                InvestImportRow.objects.create(
                    batch=batch,
                    row_number=row_number,
                    action=InvestImportRow.Action.NEW_PROJECT,
                    payload=payload,
                )
            else:
                changes = _project_diff(existing, data)
                if not changes:
                    continue
                row_number += 1
                InvestImportRow.objects.create(
                    batch=batch,
                    row_number=row_number,
                    action=InvestImportRow.Action.CHANGED_PROJECT,
                    payload={"changes": changes, **payload},
                    target_project=existing,
                )

    gap_num = row_number
    for project in InvestProject.objects.filter(subsystem=subsystem, organization=organization):
        if project.code not in imported_codes:
            gap_num += 1
            InvestImportRow.objects.create(
                batch=batch,
                row_number=gap_num,
                action=InvestImportRow.Action.GAP,
                payload={"code": project.code, "name": project.name},
                target_project=project,
            )

    for site in InvestSite.objects.filter(subsystem=subsystem, organization=organization):
        if site.cadastral_number not in imported_cadastral:
            gap_num += 1
            InvestImportRow.objects.create(
                batch=batch,
                row_number=gap_num,
                action=InvestImportRow.Action.GAP,
                payload={"cadastral_number": site.cadastral_number, "name": site.name},
                target_site=site,
            )

    return batch


@transaction.atomic
def apply_row(row, *, user):
    if row.resolution != InvestImportRow.Resolution.PENDING:
        raise ValueError("Строка уже обработана")

    action = row.action
    payload = row.payload or {}
    subsystem = row.batch.subsystem
    organization = row.batch.organization

    if action == InvestImportRow.Action.NEW_PROJECT:
        obj = InvestProject.objects.create(
            subsystem=subsystem,
            organization=organization,
            code=payload["code"],
            name=payload.get("name", payload["code"]),
            stage=payload.get("stage") or "lead",
            investment_amount=_parse_decimal(payload.get("investment_amount")),
        )
    elif action == InvestImportRow.Action.CHANGED_PROJECT:
        obj = row.target_project
        changes = payload.get("changes", {})
        for field, value in changes.items():
            if field == "investment_amount":
                setattr(obj, field, _parse_decimal(value))
            else:
                setattr(obj, field, value)
        obj.save()
    elif action == InvestImportRow.Action.NEW_SITE:
        obj = InvestSite.objects.create(
            subsystem=subsystem,
            organization=organization,
            cadastral_number=payload["cadastral_number"],
            name=payload.get("name", payload["cadastral_number"]),
            status=payload.get("status") or InvestSite.Status.DRAFT,
        )
    elif action == InvestImportRow.Action.CHANGED_SITE:
        obj = row.target_site
        changes = payload.get("changes", {})
        for field, value in changes.items():
            setattr(obj, field, value)
        obj.save()
    elif action == InvestImportRow.Action.GAP:
        raise ValueError("Строка gap не применяется — пропустите или обработайте вручную")
    else:
        raise ValueError(f"Неизвестное действие: {action}")

    row.resolution = InvestImportRow.Resolution.APPLIED
    row.applied_at = timezone.now()
    row.save(update_fields=["resolution", "applied_at"])
    return obj


def skip_row(row):
    if row.resolution != InvestImportRow.Resolution.PENDING:
        raise ValueError("Строка уже обработана")
    row.resolution = InvestImportRow.Resolution.SKIPPED
    row.save(update_fields=["resolution"])
