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
        {"code": "M48", "title": "Семантический поиск", "note": "Knowledge base + гибридный поиск"},
        {"code": "M49", "title": "Классификация обращений", "note": "Тематики УЖВ, маршрут, explainability"},
        {"code": "M51", "title": "OCR и NER", "note": "PDF/DOCX/TXT/изображения → текст; поля заявления УЖВ, HITL"},
        {"code": "M52", "title": "Полнота пакета", "note": "Чек-лист документов по типу дела"},
        {"code": "M53", "title": "Черновики ответов", "note": "Human-in-the-loop перед публикацией"},
        {"code": "M54", "title": "Аномалии / риски", "note": "Просрочки, дашборды контроля"},
    ]


def build_ai_module_doc(subsystem: Subsystem | None = None) -> dict:
    """Описание модуля ИИ для экспертизы реестра (AI-P0-12)."""
    from delayu.models import AiPolicy

    policy = None
    if subsystem:
        policy = AiPolicy.objects.filter(subsystem=subsystem).first()

    return {
        "product_name": "ДелаЮ",
        "vendor": "ЮГИт",
        "version": platform_version(),
        "subsystem": subsystem,
        "policy": policy,
        "generated_at": timezone.now(),
        "functions": [
            {
                "id": "ИИ-1",
                "title": "Классификация и маршрутизация обращений",
                "description": (
                    "Автоматическое определение тематики входящего обращения (жалоба, заявление "
                    "малоимущих, жилфонд, переселение, дети-сироты, прочее) и рекомендуемого "
                    "маршрута (роль/подразделение). Результат с confidence и списком причин "
                    "отображается оператору; сохранение — только после подтверждения (HITL)."
                ),
                "screens": ["/uzhv/appeals/new/", "/uzhv/appeals/<id>/edit/"],
                "apis": ["POST /uzhv/appeals/classify-preview/"],
                "audit": "ai.classify, AiRequestLog",
            },
            {
                "id": "ИИ-2",
                "title": "OCR и извлечение реквизитов (NER)",
                "description": (
                    "Распознавание текста из PDF, DOCX, TXT и изображений (Tesseract при наличии). "
                    "Извлечение полей заявления УЖВ: ФИО, СНИЛС, паспорт, адрес, телефон, "
                    "состав семьи, доход, дата заявления. Предзаполнение карточки гражданина/дела "
                    "после проверки оператором."
                ),
                "screens": ["/uzhv/cases/<id>/low-income/", "/ai/ocr/"],
                "apis": [
                    "POST /documents/<id>/ocr-preview/",
                    "POST /uzhv/cases/<id>/attachments/<id>/ocr-preview/",
                    "POST /uzhv/cases/<id>/ocr-apply/",
                ],
                "audit": "ai.ocr.preview, AiHumanReview",
            },
            {
                "id": "ИИ-3",
                "title": "Контроль полноты комплекта документов",
                "description": (
                    "Проверка наличия обязательных документов по типу дела; виджет «Не хватает: …» "
                    "на карточке 360°. Базовый чек-лист реализован; расширение по регламентам НСИ — в P0."
                ),
                "screens": ["/ai/tools/", "/cases/<id>/"],
                "apis": ["case_completeness (сервис ai)"],
                "audit": "AiRequestLog",
            },
            {
                "id": "ИИ-4",
                "title": "Семантический поиск",
                "description": (
                    "Гибридный полнотекстовый и векторный поиск по делам, документам и базе знаний "
                    "(SearchIndexEntry, pgvector). Строка поиска в реестрах УЖВ и модуле /ai/search/."
                ),
                "screens": ["/ai/search/", "/platform/search/"],
                "apis": ["semantic_search, reindex_search"],
                "audit": "AiRequestLog",
            },
            {
                "id": "ИИ-5",
                "title": "Прогноз сроков и контроль аномалий",
                "description": (
                    "Оценка риска просрочки, дашборд просроченных обращений и комментарии к отчётности. "
                    "Решения принимает исполнитель; ИИ формирует подсказки."
                ),
                "screens": ["/analytics/ai-risks/", "/analytics/overdue/"],
                "apis": ["predict_due_date, risk_overdue"],
                "audit": "AiRequestLog",
            },
            {
                "id": "ИИ-6",
                "title": "Черновики ответов и документов",
                "description": (
                    "Генерация черновика ответа на обращение из шаблона и данных карточки. "
                    "Публикация только после редактирования человеком."
                ),
                "screens": ["/uzhv/appeals/", "/ai/assistant/"],
                "apis": ["assistant_chat, draft_response"],
                "audit": "AiRequestLog, AiHumanReview",
            },
            {
                "id": "ИИ-7",
                "title": "Журнал ИИ и аудит",
                "description": (
                    "Журнал запросов к ИИ (модуль, промпт, результат, пользователь), очередь HITL, "
                    "политики AiPolicy (лимиты, allow_pii, имя модели). Экспорт в общий аудит платформы."
                ),
                "screens": ["/ai/", "/ai/hitl/", "/ai/policies/", "/administration/audit/"],
                "apis": ["AiGateway (rate limit, PII mask)"],
                "audit": "AuditLog, AiRequestLog, AiHumanReview",
            },
        ],
        "principles": [
            "Решения по персональным данным и исходящим документам принимает человек (HITL).",
            "Все обращения к ИИ логируются в AiRequestLog с привязкой к подсистеме и пользователю.",
            "ИИ можно отключить на уровне подсистемы (AiPolicy) без остановки ядра платформы.",
            "OCR для сканов требует Tesseract (rus) в контуре заказчика; PDF/DOCX работают без него.",
        ],
        "stack": [
            {"layer": "OCR", "tech": "pypdf, python-docx, Pillow, опционально Tesseract"},
            {"layer": "NER УЖВ", "tech": "Правила + regex (uzhv_ner.py), расширяемо ML"},
            {"layer": "Классификация", "tech": "Rule-based + keyword (classify_correspondence)"},
            {"layer": "Поиск", "tech": "PostgreSQL FTS + pgvector embeddings"},
            {"layer": "Шлюз", "tech": "AiGateway: лимиты, маскирование PII, AiPolicy"},
        ],
    }


def export_ai_module_pdf(subsystem: Subsystem | None) -> HttpResponse:
    from delayu.services.uzhv_export import rows_to_pdf_bytes

    data = build_ai_module_doc(subsystem)
    rows = [
        ["Параметр", "Значение"],
        ["Продукт", data["product_name"]],
        ["Модуль", "Интеллектуальная обработка данных (M47–M56)"],
        ["Версия", data["version"]],
        ["Правообладатель", data["vendor"]],
        ["", ""],
        ["ID", "Функция", "Экраны"],
    ]
    for fn in data["functions"]:
        screens = ", ".join(fn["screens"][:2])
        rows.append([fn["id"], fn["title"], screens])
    rows.append(["", "", ""])
    rows.append(["Принцип", ""])
    for p in data["principles"]:
        rows.append([p, ""])
    title = f"Модуль ИИ — {data['product_name']} v{data['version']}"
    content = rows_to_pdf_bytes(title, rows)
    resp = HttpResponse(content, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="delayu_ai_module_{data["version"]}.pdf"'
    return resp


def build_registry_demo_guide(subsystem: Subsystem | None = None) -> dict:
    """Пошаговый сценарий для экспертизы реестра (DEMO-P0-02, REG-P0-02)."""
    from django.conf import settings

    from delayu.models_uzhv import HousingQueueCase

    demo_case = None
    if subsystem:
        demo_case = HousingQueueCase.objects.filter(
            subsystem=subsystem, case_number="УЖВ-DEMO-REG"
        ).first()

    base_url = getattr(settings, "DELAYU_DEMO_BASE_URL", "").rstrip("/") or ""

    def url(path: str) -> str:
        return f"{base_url}{path}" if base_url else path

    demo_case_path = (
        f"/uzhv/cases/{demo_case.pk}/low-income/" if demo_case else "/uzhv/cases/"
    )

    return {
        "product_name": "ДелаЮ",
        "vendor": "ЮГИт",
        "version": platform_version(),
        "base_url": base_url or "https://<ваш-демо-стенд>",
        "demo_case_number": demo_case.case_number if demo_case else "УЖВ-DEMO-REG",
        "demo_case_id": demo_case.pk if demo_case else None,
        "credentials": [
            {"role": "Специалист УЖВ", "login": "uzhv_spec", "password": "uzhv_spec"},
            {"role": "Администратор", "login": "uzhv_admin", "password": "uzhv_admin"},
        ],
        "admin_notes": [
            "Развёртывание: Python 3.12+, PostgreSQL 14+, `pip install -r requirements.txt`.",
            "Миграции: `python manage.py migrate`.",
            "Демо-данные: `python manage.py seed_registry_demo`.",
            "Проверка маршрутов: `python manage.py verify_platform`.",
            "OCR сканов: установите Tesseract с языком rus (опционально).",
        ],
        "steps": [
            {
                "n": 1,
                "title": "Классификация обращения (ИИ-1)",
                "path": url("/uzhv/appeals/new/"),
                "hint": "Шаг 2: тема «Жалоба на срок…» — панель классификации с маршрутом и ролью.",
            },
            {
                "n": 2,
                "title": "OCR заявления (ИИ-2)",
                "path": url(demo_case_path),
                "hint": "Откройте вложение «Заявление» → кнопка ИИ → проверьте поля → Применить.",
            },
            {
                "n": 3,
                "title": "Полнота пакета (ИИ-3)",
                "path": url(demo_case_path),
                "hint": "Виджет «Полнота комплекта» покажет недостающие справки о доходах и имуществе.",
            },
            {
                "n": 4,
                "title": "Семантический поиск (ИИ-4)",
                "path": url("/ai/search/?q=малоимущие+заявление"),
                "hint": "Поиск по базе знаний и индексу платформы.",
            },
            {
                "n": 5,
                "title": "Черновик ответа / печать (ИИ-6)",
                "path": url("/uzhv/appeals/"),
                "hint": "Откройте демо-обращение → «Черновик ответа (ИИ)» → правка → docx/PDF.",
            },
            {
                "n": 6,
                "title": "Риски сроков (ИИ-5)",
                "path": url("/analytics/ai-risks/"),
                "hint": "Просроченные обращения и heatmap исполнителей.",
            },
            {
                "n": 7,
                "title": "Журнал ИИ (ИИ-7)",
                "path": url("/ai/hitl/"),
                "hint": "Подтверждения OCR и классификации; также `/administration/audit/`.",
            },
        ],
        "doc_urls": [
            {"label": "Документация для реестра", "path": url("/docs/registry/")},
            {"label": "Тексты заявления", "path": url("/docs/registry/application/")},
            {"label": "Модуль ИИ", "path": url("/docs/registry/ai/")},
            {"label": "Паспорт продукта", "path": url("/docs/registry/passport/")},
        ],
        "screencast_lines": [
            "1. Войти на демо-стенд под uzhv_spec / uzhv_spec.",
            "2. Создать обращение (/uzhv/appeals/new/) — показать подсказку классификации ИИ.",
            "3. Открыть дело УЖВ-DEMO-REG → OCR вложения «Заявление» → HITL «Применить».",
            "4. Показать виджет полноты пакета на карточке дела.",
            "5. Семантический поиск: /ai/search/?q=малоимущие.",
            "6. Черновик ответа на демо-обращении — без автопубликации.",
            "7. Дашборд рисков /analytics/ai-risks/ и журнал /ai/hitl/.",
        ],
        "generated_at": timezone.now(),
    }


def _registry_base_url() -> str:
    from django.conf import settings

    return (
        getattr(settings, "DELAYU_PUBLIC_SITE_URL", "").rstrip("/")
        or getattr(settings, "DELAYU_DEMO_BASE_URL", "").rstrip("/")
        or ""
    )


def resolve_registry_subsystem() -> Subsystem | None:
    """Подсистема для публичной документации реестра (демо УЖВ)."""
    return (
        Subsystem.objects.filter(code="uzhv").first()
        or Subsystem.objects.filter(industry_template="uzhv").first()
        or Subsystem.objects.order_by("pk").first()
    )


def build_public_registry_hub() -> dict:
    """Главная публичная страница документации для реестра Минцифры."""
    from delayu.models import PlatformReleaseVersion

    subsystem = resolve_registry_subsystem()
    demo = build_registry_demo_guide(subsystem)
    passport = build_product_passport(subsystem)
    releases = list(PlatformReleaseVersion.objects.all()[:6])
    site = _registry_base_url() or "https://delau.tech"

    return {
        "product_name": "ДелаЮ",
        "vendor": "ЮГИт",
        "version": platform_version(),
        "site_url": site,
        "demo_url": getattr(settings, "DELAYU_DEMO_BASE_URL", "").rstrip("/") or site,
        "passport": passport,
        "demo": demo,
        "releases": releases,
        "deploy_notes": [
            "Обновления на delau.tech: выпуск релиза правообладателем → доставка на сервер "
            "по защищённому каналу (SSH/API) → установка зависимостей и миграции БД.",
            "На сервере: `pip install -r requirements.txt`, `python manage.py migrate`, "
            "`python manage.py collectstatic --noinput`, перезапуск Gunicorn.",
            "Проверка после обновления: `python manage.py verify_platform`.",
        ],
        "registry_form_url": f"{site}/docs/registry/",
        "tariff_policy_url": f"{site}/docs/registry/tariffs/",
        "generated_at": timezone.now(),
    }


def build_tariff_policy() -> dict:
    """Тарифная политика для реестра Минцифры (коммерческая лицензия)."""
    site = _registry_base_url() or "https://delau.tech"

    return {
        "product_name": "ДелаЮ",
        "product_line": "Дела.ЮГИт",
        "vendor": "ЮГИт",
        "version": platform_version(),
        "site_url": site,
        "policy_url": f"{site}/docs/registry/tariffs/",
        "effective_date": timezone.now().date(),
        "generated_at": timezone.now(),
        "summary": (
            "Программный комплекс «ДелаЮ» распространяется на коммерческой основе "
            "по лицензионному договору. Не является open source и не распространяется безвозмездно."
        ),
        "components": [
            {
                "title": "Лицензия на использование",
                "text": (
                    "Предоставление права использования платформы «ДелаЮ» и выбранных модулей "
                    "(M01–M86) и отраслевых конфигураций (в т.ч. «АИС УЖВ»). "
                    "Модель: годовая или бессрочная лицензия — по договору."
                ),
            },
            {
                "title": "Внедрение и настройка",
                "text": (
                    "Работы по развёртыванию, настройке процессов, миграции данных, "
                    "обучению пользователей — по отдельной смете в зависимости от объёма."
                ),
            },
            {
                "title": "Пилотный проект",
                "text": (
                    "Ограниченный по сроку (30–60 дней) и функционалу стенд для одного "
                    "согласованного сценария — стоимость по смете после демонстрации."
                ),
            },
            {
                "title": "Техническое сопровождение",
                "text": (
                    "Обновления, консультации, регламентная поддержка — по договору "
                    "сопровождения (% от лицензии или фиксированная плата в месяц)."
                ),
            },
        ],
        "pricing_factors": [
            "состав и число подключённых модулей платформы;",
            "отраслевая конфигурация (ядро, «АИС УЖВ», иные модули);",
            "количество пользователей и подсистем (tenant);",
            "модель размещения (облако правообладателя / инфраструктура заказчика);",
            "объём доработок и интеграций;",
            "срок и уровень SLA сопровождения.",
        ],
        "gov_procurement": (
            "Для органов власти и муниципальных заказчиков стоимость определяется "
            "в соответствии с закупочной документацией (44-ФЗ / 223-ФЗ) и указывается "
            "в извещении и контракте. Ориентировочная стоимость лицензии и работ "
            "формируется правообладателем для расчёта НМЦК и уточняется в КП."
        ),
        "commercial": (
            "Коммерческим организациям стоимость определяется по коммерческому "
            "предложению правообладателя с учётом факторов настоящей тарифной политики."
        ),
        "demo_note": (
            f"Демо-экземпляр на {site} предназначен для ознакомления и экспертизы "
            "функционала и не является публичной офертой."
        ),
        "disclaimer": (
            "Настоящий документ описывает принципы формирования стоимости и не является "
            "публичной офертой в смысле ст. 437 ГК РФ. Итоговая цена фиксируется "
            "в лицензионном договоре / контракте / коммерческом предложении."
        ),
    }


def build_source_code_infra_doc() -> dict:
    """Исходный/объектный код и сборка — документ для реестра Минцифры."""
    site = _registry_base_url() or "https://delau.tech"

    return {
        "product_name": "ДелаЮ",
        "vendor": "ЮГИт",
        "version": platform_version(),
        "site_url": site,
        "policy_url": f"{site}/docs/registry/source-code/",
        "effective_date": timezone.now().date(),
        "generated_at": timezone.now(),
        "source_storage": (
            "Исходный текст программного комплекса «ДелаЮ» хранится в централизованном "
            "хранилище исходного кода правообладателя (ЮГИт) на технических средствах, "
            "расположенных в Российской Федерации. Состав: исходные тексты на Python "
            "(приложение Django), HTML-шаблоны, JavaScript, CSS, SQL-миграции, "
            "конфигурационные файлы, эксплуатационная документация. Доступ ограничен "
            "уполномоченными сотрудниками правообладателя. Резервное копирование — "
            "по внутреннему регламенту правообладателя."
        ),
        "object_storage": (
            f"Объектный (исполняемый) код размещается на сервере эксплуатации в РФ "
            f"(экземпляр {site}): байт-код Python, собранные статические ресурсы Django "
            "(collectstatic), зависимости в виртуальном окружении Python (.venv). "
            "Каталог развёртывания: /opt/delayu. Среда: Python 3.12+, Gunicorn, "
            "PostgreSQL 14+, Nginx."
        ),
        "build_tools": (
            "Формирование исполняемого комплекта: интерпретатор Python 3.12+ (byte-compile), "
            "менеджер пакетов pip (requirements.txt), команды Django (migrate, collectstatic). "
            "При сборке клиентских ресурсов — Node.js/npm (при необходимости). "
            "Отдельный компилятор C/C++ для ядра платформы не используется. "
            "Обновление экземпляра: доставка релиза на сервер по защищённому каналу, "
            "установка зависимостей, миграция БД, сбор статики, перезапуск Gunicorn."
        ),
        "location_address": (
            "Российская Федерация. Исходный текст: хранилище на технических средствах "
            f"правообладателя (ЮГИт) в РФ; рабочие копии — на рабочих местах разработчиков в РФ. "
            f"Объектный код: сервер {site}, каталог /opt/delayu."
        ),
        "license_keys": (
            "Активация, выпуск, распространение и управление лицензионными ключами "
            "(аппаратные dongle, serial key, онлайн-активация) не осуществляется. "
            "Права использования — по лицензионному договору. Учёт модулей и срока прав "
            "ведётся в платформе (M83, LicenseEntitlement в PostgreSQL). Отдельные технические "
            "средства генерации и проверки ключей не применяются."
        ),
        "license_location": (
            "Не применимо — отдельный сервер лицензионных ключей отсутствует. "
            f"Учёт прав: в составе экземпляра ПО на сервере {site} (РФ)."
        ),
    }


def export_source_code_infra_pdf() -> HttpResponse:
    from delayu.services.uzhv_export import rows_to_pdf_bytes

    data = build_source_code_infra_doc()
    rows = [
        ["Раздел", "Описание"],
        ["Продукт", f"{data['product_name']} v{data['version']}"],
        ["Правообладатель", data["vendor"]],
        ["Дата", data["effective_date"].strftime("%d.%m.%Y")],
        ["Хранение исходного текста", data["source_storage"]],
        ["Хранение объектного кода", data["object_storage"]],
        ["Средства сборки", data["build_tools"]],
        ["Адрес (исходный/объектный код)", data["location_address"]],
        ["Лицензионные ключи", data["license_keys"]],
        ["Адрес (лиценз. ключи)", data["license_location"]],
    ]
    title = f"Техсредства хранения и сборки — {data['product_name']} v{data['version']}"
    content = rows_to_pdf_bytes(title, rows, portrait=True)
    resp = HttpResponse(content, content_type="application/pdf")
    resp["Content-Disposition"] = (
        f'attachment; filename="delayu_source_infra_{data["version"]}.pdf"'
    )
    return resp


def export_tariff_policy_pdf() -> HttpResponse:
    from delayu.services.uzhv_export import rows_to_pdf_bytes

    data = build_tariff_policy()
    rows = [
        ["Параметр", "Значение"],
        ["Продукт", data["product_name"]],
        ["Линейка", data["product_line"]],
        ["Правообладатель", data["vendor"]],
        ["Версия", data["version"]],
        ["Дата", data["effective_date"].strftime("%d.%m.%Y")],
        ["", ""],
        ["Раздел", "Содержание"],
    ]
    rows.append(["Общие положения", data["summary"]])
    for comp in data["components"]:
        rows.append([comp["title"], comp["text"]])
    rows.append(["", ""])
    rows.append(["Факторы формирования стоимости", ""])
    for i, factor in enumerate(data["pricing_factors"], 1):
        rows.append([f"{i}.", factor])
    rows.append(["Государственные заказчики", data["gov_procurement"]])
    rows.append(["Коммерческие заказчики", data["commercial"]])
    rows.append(["Демо-экземпляр", data["demo_note"]])
    rows.append(["Оговорка", data["disclaimer"]])
    title = f"Тарифная политика — {data['product_name']} v{data['version']}"
    content = rows_to_pdf_bytes(title, rows, portrait=True)
    resp = HttpResponse(content, content_type="application/pdf")
    resp["Content-Disposition"] = (
        f'attachment; filename="delayu_tariff_policy_{data["version"]}.pdf"'
    )
    return resp


def _abs_url(path: str) -> str:
    base = _registry_base_url()
    return f"{base}{path}" if base else path


def build_registry_application(subsystem: Subsystem | None = None) -> dict:
    """Тексты полей заявления в реестр Минцифры (REG-P0-01)."""
    from django.conf import settings

    demo = build_registry_demo_guide(subsystem)
    ai_doc = build_ai_module_doc(subsystem)
    base_url = _registry_base_url() or "https://<ваш-демо-стенд>"

    ai_paragraph = (
        "Программный комплекс «ДелаЮ» включает модуль «Интеллектуальная обработка данных» "
        "(M47–M56), реализующий функции: автоматическая классификация и маршрутизация обращений "
        "по тематикам жилищного учёта (жалоба, малоимущие, жилфонд, переселение, дети-сироты) "
        "с указанием confidence и причин; OCR загруженных документов (PDF, DOCX, TXT, изображения) "
        "и извлечение реквизитов заявлений (ФИО, СНИЛС, паспорт, адрес, доход, состав семьи); "
        "контроль полноты комплекта документов по типу дела; семантический поиск по делам и "
        "базе знаний; дашборд рисков просрочки обращений; формирование черновиков ответов. "
        "Все результаты ИИ применяются только после подтверждения пользователем (HITL); "
        "запросы журналируются в AiRequestLog; политика AiPolicy задаёт лимиты и возможность "
        "отключения ИИ на уровне подсистемы."
    )

    functional_text = (
        "Программный комплекс «ДелаЮ» (линейка «Дела.ЮГИт») предназначен для автоматизации "
        "учёта обращений, заявлений и дел, ведения реестров, документооборота, контроля сроков, "
        "формирования отчётности и администрирования пользователей в веб-среде. "
        "Отраслевая конфигурация «АИС УЖВ» обеспечивает жилищный учёт: малоимущие граждане, "
        "очередь, жилфонд, договоры, обращения граждан (SLA 30 дней), жилищный контроль, отчёты. "
        "Платформа имеет модульную архитектуру (M01–M86), REST API, журнал аудита, ролевую модель."
    )

    rospatent = getattr(settings, "DELAYU_ROSPATENT_NUMBER", "") or "№ ___ (свидетельство Роспатент)"

    fields = [
        {
            "id": "product_name",
            "label": "Наименование программного обеспечения",
            "value": "ДелаЮ (Дела.ЮГИт)",
        },
        {
            "id": "vendor",
            "label": "Правообладатель",
            "value": "ЮГИт",
        },
        {
            "id": "class",
            "label": "Класс программного обеспечения",
            "value": "09.01 — Системы управления бизнес-процессами (BPM)",
        },
        {
            "id": "okpd2",
            "label": "Код ОКПД2",
            "value": "62.01.29.000 — услуги по проектированию и разработке прикладного программного "
            "обеспечения на заказ; дополнительно 58.29.32 — издание прикладного ПО",
        },
        {
            "id": "functional",
            "label": "Описание функциональных характеристик",
            "value": functional_text,
        },
        {
            "id": "ai_usage",
            "label": "Использование технологий искусственного интеллекта",
            "value": ai_paragraph,
        },
        {
            "id": "demo_url",
            "label": "Адрес экземпляра программного обеспечения для экспертизы",
            "value": base_url,
        },
        {
            "id": "docs_site",
            "label": "Публичная документация (функции, установка, эксплуатация)",
            "value": _abs_url("/docs/registry/"),
        },
        {
            "id": "demo_guide",
            "label": "Инструкция администратора / сценарий проверки",
            "value": _abs_url("/docs/registry/demo/"),
        },
        {
            "id": "tariff_policy",
            "label": "Тарифная политика (документ)",
            "value": _abs_url("/docs/registry/tariffs/"),
        },
        {
            "id": "source_infra",
            "label": "Хранение исходного/объектного кода и сборка (документ)",
            "value": _abs_url("/docs/registry/source-code/"),
        },
        {
            "id": "ai_doc",
            "label": "Документация модуля ИИ",
            "value": _abs_url("/ai/module/"),
        },
        {
            "id": "passport",
            "label": "Паспорт продукта",
            "value": _abs_url("/exploit/product-passport/"),
        },
        {
            "id": "rospatent",
            "label": "Свидетельство о регистрации программы для ЭВМ (Роспатент)",
            "value": rospatent,
        },
        {
            "id": "version",
            "label": "Версия",
            "value": platform_version(),
        },
    ]

    return {
        "product_name": "ДелаЮ",
        "vendor": "ЮГИт",
        "version": platform_version(),
        "base_url": base_url,
        "rospatent": rospatent,
        "fields": fields,
        "ai_functions": ai_doc["functions"],
        "demo_steps": demo["steps"],
        "screencast_script": demo["steps"],
        "checklist": [
            "Класс 09.01 и ОКПД2 62.01.29.000 указаны в заявлении",
            "Текст об ИИ совпадает с /ai/module/ и поведением на стенде",
            f"URL стенда доступен: {base_url}",
            "Логин uzhv_spec / uzhv_spec работает",
            "HITL: OCR и черновики не сохраняются без кнопки пользователя",
            "Журнал ИИ (/ai/hitl/) содержит записи после демо",
        ],
        "generated_at": timezone.now(),
    }


def export_registry_application_pdf(subsystem: Subsystem | None) -> HttpResponse:
    from delayu.services.uzhv_export import rows_to_pdf_bytes

    data = build_registry_application(subsystem)
    rows = [["Поле", "Значение для заявления в реестр"]]
    for f in data["fields"]:
        rows.append([f["label"], f["value"]])
    title = f"Заявление реестр — {data['product_name']} v{data['version']}"
    content = rows_to_pdf_bytes(title, rows, portrait=True)
    resp = HttpResponse(content, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="delayu_registry_application_{data["version"]}.pdf"'
    return resp


def export_demo_guide_pdf(subsystem: Subsystem | None) -> HttpResponse:
    from delayu.services.uzhv_export import rows_to_pdf_bytes

    data = build_registry_demo_guide(subsystem)
    rows = [["Шаг", "Действие", "URL"]]
    for step in data["steps"]:
        hint = step.get("hint", "")
        action = step["title"] + (f". {hint}" if hint else "")
        rows.append([str(step["n"]), action, step["path"]])
    rows.append(["", "", ""])
    rows.append(["Логин", "Пароль", "Роль"])
    for c in data["credentials"]:
        rows.append([c["login"], c["password"], c["role"]])
    title = f"Демо-сценарий {data['product_name']} v{data['version']}"
    content = rows_to_pdf_bytes(title, rows)
    resp = HttpResponse(content, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="delayu_demo_guide_{data["version"]}.pdf"'
    return resp


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
    base_url = _registry_base_url()
    rospatent = getattr(settings, "DELAYU_ROSPATENT_NUMBER", "") or ""

    return {
        "product_name": "ДелаЮ",
        "vendor": "ЮГИт",
        "version": current.version if current else platform_version(),
        "version_title": current.title if current else "Платформа управления делами",
        "released_at": current.released_at if current else None,
        "registry_class": "09.01 — Системы управления бизнес-процессами (BPM)",
        "okpd2": "62.01.29.000 — услуги по проектированию и разработке прикладного ПО на заказ",
        "demo_base_url": base_url or "— (задайте DELAYU_DEMO_BASE_URL)",
        "rospatent": rospatent or "— (задайте DELAYU_ROSPATENT_NUMBER)",
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
        "screen_paths": ["/ai/assistant/", "/ai/module/"],
        "evidence_notes": "ИИ-ассистент, AiPolicy, AI Gateway (лимиты, PII)",
    },
    "M51": {
        "screen_paths": ["/ai/ocr/", "/uzhv/low-income/"],
        "api_paths": [
            "/documents/<pk>/ocr-preview/",
            "/uzhv/cases/<pk>/attachments/<att_pk>/ocr-preview/",
            "/uzhv/cases/<pk>/ocr-apply/",
        ],
        "evidence_notes": "OCR pypdf/DOCX/Tesseract; NER uzhv_ner; HITL apply",
    },
    "M69": {
        "screen_paths": ["/infra/sso/", "/auth/sso/"],
        "evidence_notes": "SSO OIDC demo + production token exchange",
    },
    "M78": {
        "screen_paths": [
            "/exploit/product-passport/",
            "/exploit/demo-guide/",
            "/exploit/registry-application/",
        ],
        "evidence_notes": "Паспорт продукта, демо-сценарий, тексты заявления в реестр",
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
