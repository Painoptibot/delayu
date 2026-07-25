from django.db import transaction

from delayu.models_invest import InvestPackage, InvestPackageItem, InvestPackageSnapshot

DEFAULT_CHECKLIST: list[tuple[str, str, bool]] = [
    ("egrn", "Выписка ЕГРН", True),
    ("isogd", "Материалы ИСОГД", True),
    ("rgis", "Данные РГИС", True),
    ("oiv", "Запросы ОИВ", True),
    ("focus", "Контур.Фокус", True),
    ("anketa", "Анкета инвестора", True),
    ("measures", "Меры господдержки", True),
    ("protocol", "Протокол о намерениях", True),
]


@transaction.atomic
def ensure_package(project) -> InvestPackage:
    pkg = InvestPackage.objects.filter(project=project, is_active=True).first()
    if pkg:
        return pkg
    pkg = InvestPackage.objects.create(project=project, is_active=True)
    InvestPackageItem.objects.bulk_create(
        [
            InvestPackageItem(
                package=pkg,
                code=code,
                title=title,
                required=required,
                status=InvestPackageItem.Status.MISSING,
            )
            for code, title, required in DEFAULT_CHECKLIST
        ]
    )
    return pkg


def set_item_status(item, status, attachment=None, document=None):
    item.status = status
    update_fields = ["status"]
    if attachment is not None:
        item.file = attachment
        update_fields.append("file")
    if document is not None:
        item.document = document
        update_fields.append("document")
    item.save(update_fields=update_fields)
    return item


def snapshot_package(project, *, handoff=None, decision: str = "") -> InvestPackageSnapshot:
    pkg = ensure_package(project)
    items = [
        {
            "code": item.code,
            "title": item.title,
            "required": item.required,
            "status": item.status,
            "status_label": item.get_status_display(),
            "file": item.file.name if item.file else "",
            "document_id": item.document_id,
            "document_title": item.document.title if item.document_id else "",
            "due_at": item.due_at.isoformat() if item.due_at else None,
        }
        for item in pkg.items.select_related("document").order_by("id")
    ]
    payload = {
        "project": {"id": project.pk, "code": project.code, "name": project.name},
        "decision": decision,
        "handoff_id": handoff.pk if handoff else None,
        "handoff_comment": handoff.comment if handoff else "",
        "items": items,
    }
    return InvestPackageSnapshot.objects.create(
        project=project,
        package=pkg,
        handoff=handoff,
        decision=decision,
        payload=payload,
    )


def package_is_ready(project) -> bool:
    pkg = InvestPackage.objects.filter(project=project, is_active=True).first()
    if not pkg:
        return True
    return not pkg.items.filter(required=True, status=InvestPackageItem.Status.MISSING).exists()
