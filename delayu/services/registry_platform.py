"""Паспорт продукта и журнал соответствия реестру Минцифры."""
from __future__ import annotations

import csv
import io

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone

from delayu.models import ModuleCatalog, Subsystem, SubsystemModule


def platform_version() -> str:
    return getattr(settings, "DELAYU_PLATFORM_VERSION", "2.2.0")


def product_stack() -> list[dict]:
    return [
        {"layer": "Backend", "tech": "Python 3.12+, Django 5.x"},
        {"layer": "БД", "tech": "PostgreSQL 14+"},
        {"layer": "Frontend", "tech": "Materialize, server-side templates, JS"},
        {"layer": "API", "tech": "REST /api/v1/, OpenAPI"},
        {"layer": "Развёртывание", "tech": "Docker, Nginx, Astra Linux / Windows (dev)"},
        {"layer": "ИИ", "tech": "M47–M56, политика AiPolicy, RAG-ready"},
    ]


def ai_registry_scenarios() -> list[dict]:
    return [
        {"code": "M47", "title": "ИИ-ассистент", "note": "Подсказки по делам и документам"},
        {"code": "M19", "title": "Семантический поиск", "note": "Knowledge base + гибридный поиск"},
        {"code": "M20", "title": "Классификация", "note": "Маршрутизация обращений с объяснением"},
        {"code": "M21", "title": "Черновики", "note": "Human-in-the-loop перед публикацией"},
        {"code": "M22", "title": "Аномалии / риски", "note": "Просрочки, дашборды контроля"},
    ]


def build_product_passport(subsystem: Subsystem | None) -> dict:
    from delayu.models import GlossaryTerm, PlatformReleaseVersion

    modules_enabled = []
    if subsystem:
        links = (
            SubsystemModule.objects.filter(subsystem=subsystem, enabled=True)
            .select_related("module")
            .order_by("module__sort_order", "module__code")
        )
        modules_enabled = [link.module for link in links]
    else:
        modules_enabled = list(ModuleCatalog.objects.filter(is_active=True)[:30])

    current = PlatformReleaseVersion.objects.filter(is_current=True).first()
    releases = list(PlatformReleaseVersion.objects.all()[:8])
    compliance = compliance_rows(subsystem) if subsystem else []

    return {
        "product_name": "ДелаЮ",
        "vendor": "ЮГИт",
        "version": current.version if current else platform_version(),
        "version_title": current.title if current else "Платформа управления делами",
        "released_at": current.released_at if current else None,
        "stack": product_stack(),
        "modules_enabled": modules_enabled,
        "modules_count": len(modules_enabled),
        "ai_scenarios": ai_registry_scenarios(),
        "releases": releases,
        "compliance_rows": compliance,
        "glossary": list(GlossaryTerm.objects.all()[:50]),
        "subsystem": subsystem,
        "generated_at": timezone.now(),
    }


def compliance_rows(subsystem: Subsystem) -> list[dict]:
    from delayu.models import ModuleComplianceEntry

    enabled = (
        SubsystemModule.objects.filter(subsystem=subsystem, enabled=True)
        .select_related("module")
        .order_by("module__sort_order", "module__code")
    )
    entries = {
        e.module_id: e
        for e in ModuleComplianceEntry.objects.select_related("module").all()
    }
    rows = []
    for link in enabled:
        mod = link.module
        entry = entries.get(mod.pk)
        rows.append(
            {
                "code": mod.code,
                "name": mod.name,
                "group": mod.get_group_display(),
                "screens": entry.screen_paths if entry else [],
                "apis": entry.api_paths if entry else [],
                "roles": entry.role_notes if entry else "",
                "reports": entry.report_refs if entry else "",
                "evidence": entry.evidence_notes if entry else "",
            }
        )
    return rows


def export_compliance_csv(subsystem: Subsystem) -> HttpResponse:
    rows = compliance_rows(subsystem)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Модуль", "Наименование", "Группа", "Экраны", "API", "Роли", "Отчёты", "Доказательства"])
    for r in rows:
        w.writerow(
            [
                r["code"],
                r["name"],
                r["group"],
                ", ".join(r["screens"]),
                ", ".join(r["apis"]),
                r["roles"],
                r["reports"],
                r["evidence"],
            ]
        )
    resp = HttpResponse(buf.getvalue().encode("utf-8-sig"), content_type="text/csv; charset=utf-8")
    stamp = timezone.now().strftime("%Y%m%d")
    resp["Content-Disposition"] = f'attachment; filename="delayu_compliance_{subsystem.code}_{stamp}.csv"'
    return resp


def export_passport_pdf(subsystem: Subsystem | None) -> HttpResponse:
    from delayu.services.uzhv_export import rows_to_pdf_bytes

    data = build_product_passport(subsystem)
    rows = [
        ["Параметр", "Значение"],
        ["Продукт", data["product_name"]],
        ["Правообладатель", data["vendor"]],
        ["Версия", data["version"]],
        ["Подсистема", subsystem.name if subsystem else "—"],
        ["Модулей включено", str(data["modules_count"])],
    ]
    for item in data["stack"]:
        rows.append([item["layer"], item["tech"]])
    rows.append(["", ""])
    rows.append(["Модуль", "Наименование"])
    for mod in data["modules_enabled"][:40]:
        rows.append([mod.code, mod.name])
    title = f"Паспорт продукта {data['product_name']} v{data['version']}"
    content = rows_to_pdf_bytes(title, rows)
    resp = HttpResponse(content, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="delayu_passport_{data["version"]}.pdf"'
    return resp


DEFAULT_COMPLIANCE: dict[str, dict] = {
    "M01": {
        "screen_paths": ["/administration/subsystems/", "/administration/audit/"],
        "api_paths": ["/api/v1/health/"],
        "role_notes": "platform_admin, admin",
        "evidence_notes": "Мастер подсистем, append-only аудит, снимки CSV",
    },
    "M02": {
        "screen_paths": ["/administration/roles/", "/administration/roles-matrix/"],
        "role_notes": "admin",
        "evidence_notes": "Матрица роль × модуль × CRUD, делегирование",
    },
    "M06": {
        "screen_paths": ["/archive/cases/"],
        "evidence_notes": "Архив дел, legal hold, purge по retention",
    },
    "M07": {
        "screen_paths": ["/workspace/cabinet/", "/workspace/cabinet/security/"],
        "role_notes": "all authenticated",
        "evidence_notes": "Личный кабинет, 2FA TOTP, реестр сессий",
    },
    "M12": {
        "screen_paths": ["/administration/audit/"],
        "api_paths": ["/administration/audit/export.csv"],
        "evidence_notes": "AuditLog append-only, экспорт CSV, снимки compliance",
    },
    "M19": {
        "screen_paths": ["/ai/search/"],
        "evidence_notes": "SearchIndexEntry, pgvector-ready, гибридный поиск",
    },
    "M22": {
        "screen_paths": ["/cases/"],
        "api_paths": ["/api/v1/cases/"],
        "evidence_notes": "Реестр дел, карточка 360°, архив",
    },
    "M33": {
        "screen_paths": ["/bpm/instances/"],
        "evidence_notes": "BPM экземпляры, согласования",
    },
    "M43": {
        "api_paths": ["/api/v1/openapi.json", "/api/v1/health/"],
        "evidence_notes": "REST API Gateway, Bearer-ключи, rate limit, OpenAPI",
    },
    "M47": {
        "screen_paths": ["/ai/assistant/"],
        "evidence_notes": "ИИ-ассистент, AiPolicy, AI Gateway (лимиты, PII)",
    },
    "M69": {
        "screen_paths": ["/infra/sso/", "/auth/sso/"],
        "evidence_notes": "SSO OIDC demo + production token exchange",
    },
    "M78": {
        "screen_paths": ["/exploit/"],
        "evidence_notes": "Шаблоны уведомлений, почта, ПДн",
    },
}


DEFAULT_GLOSSARY = [
    ("Дело", "Универсальная карточка учёта заявления, обращения или процесса в платформе «ДелаЮ»."),
    ("Подсистема", "Изолированный контур заказчика: модули, роли, меню и данные (tenant)."),
    ("Маршрут", "Последовательность шагов BPM/workflow с SLA и исполнителями."),
    ("НСИ", "Нормативно-справочная информация: классификаторы и значения."),
    ("Реестр", "Типизированный набор записей по JSON-схеме (M23)."),
    ("Исполнитель", "Пользователь, ответственный за срок и результат по объекту учёта."),
    ("ПДн", "Персональные данные; маскирование и права view_pii/export_pii."),
    ("Конфигурация", "Профиль отрасли (core, uzhv, …): модули и меню без пересборки."),
]


def seed_registry_catalog() -> dict:
    """Заполнить релиз, глоссарий и записи соответствия (идемпотентно)."""
    from delayu.models import GlossaryTerm, ModuleComplianceEntry, PlatformReleaseVersion

    rel, _ = PlatformReleaseVersion.objects.update_or_create(
        version=platform_version(),
        defaults={
            "released_at": timezone.now().date(),
            "title": "Платформа «ДелаЮ» — реестровый контур",
            "changelog": "Паспорт продукта, журнал соответствия модулей, глоссарий.",
            "is_current": True,
        },
    )
    PlatformReleaseVersion.objects.exclude(pk=rel.pk).update(is_current=False)

    glossary_n = 0
    for idx, (term, definition) in enumerate(DEFAULT_GLOSSARY):
        _, created = GlossaryTerm.objects.update_or_create(
            term=term,
            defaults={"definition": definition, "sort_order": idx, "locale": "ru"},
        )
        if created:
            glossary_n += 1

    compliance_n = 0
    for code, payload in DEFAULT_COMPLIANCE.items():
        mod = ModuleCatalog.objects.filter(code=code).first()
        if not mod:
            continue
        ModuleComplianceEntry.objects.update_or_create(
            module=mod,
            defaults=payload,
        )
        compliance_n += 1

    return {
        "release": rel.version,
        "glossary_new": glossary_n,
        "compliance": compliance_n,
    }
