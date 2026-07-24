from django.db import transaction

from delayu.models_invest import InvestPackage, InvestPackageItem

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


def set_item_status(item, status, attachment=None):
    item.status = status
    update_fields = ["status"]
    if attachment is not None:
        item.file = attachment
        update_fields.append("file")
    item.save(update_fields=update_fields)
    return item


def package_is_ready(project) -> bool:
    pkg = InvestPackage.objects.filter(project=project, is_active=True).first()
    if not pkg:
        return True
    return not pkg.items.filter(required=True, status=InvestPackageItem.Status.MISSING).exists()
