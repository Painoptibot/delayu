"""PY-06 — ZIP-комплект документов по учётному делу."""
from __future__ import annotations

import io
import json
import zipfile
from datetime import date, datetime

from delayu.models_uzhv import HousingQueueCase, OrphanHousingRecord
from delayu.services.uzhv_timeline import build_case_timeline


def _json_default(obj):
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(type(obj))


def build_case_manifest(case: HousingQueueCase) -> dict:
    citizen = case.citizen
    timeline = build_case_timeline(case)
    manifest = {
        "case_number": case.case_number,
        "status": case.status,
        "category": case.category,
        "registered_at": case.registered_at,
        "queue_position": case.queue_position,
        "citizen": {
            "full_name": citizen.full_name,
            "snils": citizen.snils,
            "reg_address": citizen.reg_address,
            "phone": citizen.phone,
            "passport_series": citizen.passport_series,
            "passport_number": citizen.passport_number,
        },
        "low_income": {
            "eligible": case.low_income_eligible,
            "per_capita_income": str(case.per_capita_income) if case.per_capita_income is not None else None,
            "application_at": case.low_income_application_at,
            "review_due_at": case.low_income_review_due_at,
            "conclusion": case.low_income_conclusion,
        },
        "household_members": [
            {
                "full_name": m.full_name,
                "relation": m.relation,
                "monthly_income": str(m.monthly_income) if m.monthly_income is not None else None,
            }
            for m in case.household_members.all()
        ],
        "attachments": [
            {"title": a.title, "doc_kind": a.doc_kind, "filename": a.file.name.split("/")[-1]}
            for a in case.attachments.all()
        ],
        "appeals": [
            {
                "number": a.appeal_number,
                "subject": a.subject,
                "status": a.status,
                "due_date": a.due_date,
            }
            for a in case.appeals.all()[:50]
        ],
        "interagency": [
            {
                "number": r.request_number,
                "recipient": r.recipient_name,
                "status": r.status,
                "request_type": r.request_type,
            }
            for r in case.interagency_requests.all()[:50]
        ],
        "timeline": [
            {"date": e.date.isoformat(), "title": e.title, "kind": e.kind} for e in timeline
        ],
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }

    orphan = OrphanHousingRecord.objects.filter(case=case).first()
    if orphan is not None:
        manifest["orphan"] = {
            "housing_status": orphan.housing_status,
            "mintrud_decision_number": orphan.mintrud_decision_number,
            "mintrud_decision_date": orphan.mintrud_decision_date,
            "notes": orphan.notes,
        }

    return manifest


def _write_attachments(zf: zipfile.ZipFile, case: HousingQueueCase) -> None:
    for att in case.attachments.all():
        if not att.file:
            continue
        try:
            att.file.open("rb")
            data = att.file.read()
            att.file.close()
        except OSError:
            continue
        safe_name = att.file.name.split("/")[-1] or f"attachment_{att.pk}"
        zf.writestr(f"attachments/{safe_name}", data)


def build_case_zip_bytes(case: HousingQueueCase, *, include_attachments: bool = True) -> bytes:
    manifest = build_case_manifest(case)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2, default=_json_default),
        )
        summary_lines = [
            f"Дело: {case.case_number}",
            f"Гражданин: {case.citizen.full_name}",
            f"Статус: {case.get_status_display()}",
            f"Категория: {case.get_category_display()}",
            f"Очерёдность: {case.queue_position or '—'}",
            "",
            "Хронология:",
        ]
        for ev in manifest["timeline"]:
            summary_lines.append(f"  {ev['date']} — {ev['title']}")

        if manifest.get("orphan"):
            o = manifest["orphan"]
            summary_lines.extend(
                [
                    "",
                    "Дети-сироты:",
                    f"  Статус обеспечения: {o.get('housing_status', '—')}",
                    f"  Решение Минтруда: {o.get('mintrud_decision_number') or '—'}",
                ]
            )
            if o.get("mintrud_decision_date"):
                summary_lines.append(f"  Дата решения: {o['mintrud_decision_date']}")

        if case.low_income_review_due_at:
            summary_lines.extend(
                [
                    "",
                    f"Срок рассмотрения заявления (малоимущие): {case.low_income_review_due_at}",
                ]
            )

        zf.writestr("summary.txt", "\n".join(summary_lines))
        if case.low_income_conclusion:
            zf.writestr("low_income_conclusion.txt", case.low_income_conclusion)
        if case.notes:
            zf.writestr("notes.txt", case.notes)

        if manifest.get("interagency"):
            lines = ["Межведомственные запросы:"]
            for r in manifest["interagency"]:
                lines.append(
                    f"  {r['number']} — {r['recipient']} ({r['status']})"
                )
            zf.writestr("interagency.txt", "\n".join(lines))

        if include_attachments:
            _write_attachments(zf, case)

    return buf.getvalue()


def build_orphan_package_bytes(case: HousingQueueCase) -> bytes:
    """ZIP для направления «дети-сироты» (manifest + вложения + межвед + сопроводительный лист)."""
    base = build_case_zip_bytes(case, include_attachments=True)
    try:
        from delayu.services.uzhv_documents import render_case_document

        title, cover = render_case_document(case, "uzhv_orphan_package_cover")
    except KeyError:
        return base
    buf = io.BytesIO(base)
    with zipfile.ZipFile(buf, "a", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("orphan_cover.txt", cover)
    return buf.getvalue()
