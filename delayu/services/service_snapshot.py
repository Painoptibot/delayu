"""Перенос снимка локации Canadian LED в контур. Контакты сделок не копируются."""
from __future__ import annotations

from pathlib import Path

from delayu.data.canadian_led_account import ADS, FORMS, PHONES, STAFF, WORKFLOWS

FIELDS_PATH = Path(__file__).resolve().parent.parent / "data" / "canadian_led_fields.tsv"


def load_canadian_led(subsystem):
    load_workflows(subsystem)
    load_forms(subsystem)
    load_phones(subsystem)
    load_staff(subsystem)
    load_ads(subsystem)
    load_fields(subsystem)


def load_workflows(subsystem):
    from delayu.models_service import ServiceWorkflow

    for code, folder, name, status, enrolled in WORKFLOWS:
        row, created = ServiceWorkflow.objects.get_or_create(
            subsystem=subsystem,
            code=code,
            defaults={
                "folder": folder or "Без папки",
                "name": name,
                "status": status,
                "trigger": "manual",
                "action": "stored",
                "enrolled": enrolled,
            },
        )
        if not created and row.action == "stored" and row.enrolled == 0 and enrolled:
            row.enrolled = enrolled
            row.save(update_fields=["enrolled"])
    return ServiceWorkflow.objects.filter(subsystem=subsystem)


def load_forms(subsystem):
    from delayu.models_service import ServiceForm

    for folder, name, prompt, status in FORMS:
        ServiceForm.objects.get_or_create(
            subsystem=subsystem,
            name=name,
            defaults={"folder": folder, "prompt": prompt, "status": status},
        )
    return ServiceForm.objects.filter(subsystem=subsystem)


def load_phones(subsystem):
    from delayu.models_service import ServicePhone

    for number, title, forward_to, timeout in PHONES:
        ServicePhone.objects.get_or_create(
            subsystem=subsystem,
            number=number,
            defaults={"title": title, "forward_to": forward_to, "timeout_seconds": timeout},
        )
    return ServicePhone.objects.filter(subsystem=subsystem)


def load_staff(subsystem):
    from delayu.models_service import ServiceStaff

    for name, email, role_name in STAFF:
        ServiceStaff.objects.get_or_create(
            subsystem=subsystem,
            email=email,
            defaults={"name": name, "role_name": role_name},
        )
    return ServiceStaff.objects.filter(subsystem=subsystem)


def load_ads(subsystem):
    from delayu.models_service import ServiceAd

    for name, network, province, job_type, active in ADS:
        ServiceAd.objects.get_or_create(
            subsystem=subsystem,
            name=name,
            defaults={
                "network": network,
                "province": province,
                "job_type": job_type,
                "active": active,
            },
        )
    return ServiceAd.objects.filter(subsystem=subsystem)


def load_fields(subsystem):
    from delayu.models_service import ServiceField

    if not FIELDS_PATH.exists():
        return ServiceField.objects.filter(subsystem=subsystem)
    lines = FIELDS_PATH.read_text(encoding="utf-8").splitlines()
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        name, field_type, folder, key = parts[0], parts[1], parts[2], parts[3]
        key = key.strip().strip("{}")
        if key.startswith("opportunity."):
            record = ServiceField.Record.OPPORTUNITY
        elif key.startswith("business."):
            record = ServiceField.Record.COMPANY
        else:
            record = ServiceField.Record.CONTACT
        ServiceField.objects.get_or_create(
            subsystem=subsystem,
            key=key[:180],
            defaults={
                "name": name[:255],
                "field_type": field_type[:64],
                "folder": "" if folder == "—" else folder[:128],
                "record": record,
            },
        )
    return ServiceField.objects.filter(subsystem=subsystem)
