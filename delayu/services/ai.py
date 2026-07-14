"""ИИ-сервисы: rule-based + журнал (M47–M66)."""
import re

from delayu.models import AiRequestLog, CaseFile, KnowledgeArticle


def assistant_chat(subsystem, user, question: str) -> str:
    from delayu.services.ai_gateway import invoke

    def run():
        articles = KnowledgeArticle.objects.filter(subsystem=subsystem)[:20]
        hits = []
        q = question.lower()
        for a in articles:
            if q in a.body.lower() or q in a.title.lower():
                hits.append(a.title)
        if hits:
            return "По базе знаний: " + "; ".join(hits[:3])
        return (
            "По вашему вопросу рекомендую проверить регламент в разделе «База знаний» "
            "или уточнить у администратора подсистемы."
        )

    return invoke(subsystem, user, "M47", question, run)


def classify_correspondence(subject: str, body: str = "") -> dict:
    text = f"{subject} {body}".strip().lower()
    reasons: list[str] = []

    routes = {
        "Жалоба": {
            "route": "УЖВ — обращения граждан",
            "department": "Отдел регистрации обращений",
            "assignee_role": "uzhv_queue_spec",
        },
        "Малоимущие": {
            "route": "УЖВ — учёт малоимущих",
            "department": "Отдел социальной поддержки",
            "assignee_role": "uzhv_queue_spec",
        },
        "Жилищный фонд": {
            "route": "УЖВ — жилфонд",
            "department": "Отдел жилищного фонда",
            "assignee_role": "uzhv_contract_spec",
        },
        "Переселение": {
            "route": "УЖВ — переселение",
            "department": "Отдел переселения",
            "assignee_role": "uzhv_head",
        },
        "Дети-сироты": {
            "route": "УЖВ — дети-сироты",
            "department": "Отдел опеки и сирот",
            "assignee_role": "uzhv_orphan_spec",
        },
        "Договоры": {
            "route": "УЖВ — договорной отдел",
            "department": "Отдел договоров",
            "assignee_role": "uzhv_contract_spec",
        },
        "Учёт нуждающихся": {
            "route": "УЖВ — очередь",
            "department": "Отдел учёта нуждающихся",
            "assignee_role": "uzhv_queue_spec",
        },
        "Заявление": {
            "route": "УЖВ — приём заявлений",
            "department": "Отдел регистрации",
            "assignee_role": "uzhv_queue_spec",
        },
        "Справки и документы": {
            "route": "УЖВ — документооборот",
            "department": "Общий реестр",
            "assignee_role": "uzhv_queue_spec",
        },
        "Обращение": {
            "route": "УЖВ — общий реестр",
            "department": "Общий реестр",
            "assignee_role": "uzhv_queue_spec",
        },
    }

    rules: list[tuple[tuple[str, ...], str, int, float]] = [
        (("жалоб", "возмущ"), "Жалоба", 1, 0.91),
        (("малоимущ", "прожиточ", "доход"), "Малоимущие", 2, 0.90),
        (("жилфонд", "мкд", "помещен"), "Жилищный фонд", 2, 0.89),
        (("пересел", "аварийн"), "Переселение", 2, 0.88),
        (("сирот", "опек"), "Дети-сироты", 2, 0.88),
        (("договор", "найм", "соцнайм"), "Договоры", 3, 0.86),
        (("очеред", "учёт", "учет"), "Учёт нуждающихся", 2, 0.87),
        (("заяв", "заявлен"), "Заявление", 2, 0.88),
        (("справк", "выписк"), "Справки и документы", 3, 0.82),
    ]
    for markers, theme, priority, confidence in rules:
        if any(m in text for m in markers):
            reasons.append(f"маркер темы «{theme}»")
            meta = routes[theme]
            return {
                "theme": theme,
                "priority": priority,
                "route": meta["route"],
                "department": meta["department"],
                "assignee_role": meta["assignee_role"],
                "reasons": reasons,
                "confidence": confidence,
            }

    reasons.append("нет специфичных маркеров — класс «Обращение»")
    meta = routes["Обращение"]
    return {
        "theme": "Обращение",
        "priority": 3,
        "route": meta["route"],
        "department": meta["department"],
        "assignee_role": meta["assignee_role"],
        "reasons": reasons,
        "confidence": 0.72,
    }


def summarize_case(case: CaseFile) -> str:
    docs = case.documents.count()
    tasks = case.tasks.filter(completed_at__isnull=True).count()
    return (
        f"Дело {case.number}: {case.title}. Статус: {case.get_status_display()}. "
        f"Документов: {docs}, открытых задач: {tasks}."
    )


def risk_overdue(case: CaseFile) -> dict:
    from django.utils import timezone

    if not case.due_date:
        return {"risk": "low", "message": "Срок не задан"}
    today = timezone.now().date()
    if case.due_date < today and case.status not in (CaseFile.Status.DONE, CaseFile.Status.ARCHIVED):
        return {"risk": "high", "message": "Просрочено"}
    if (case.due_date - today).days <= 2:
        return {"risk": "medium", "message": "Срок истекает в ближайшие 2 дня"}
    return {"risk": "low", "message": "В норме"}


def semantic_search(subsystem, query: str) -> list[dict]:
    """Гибридный поиск: индекс + fallback по моделям."""
    from delayu.models import SearchIndexEntry
    from delayu.services.search_index import search_index

    if SearchIndexEntry.objects.filter(subsystem=subsystem).exists():
        indexed = search_index(subsystem, query)
        if indexed:
            return indexed
    return _semantic_search_fallback(subsystem, query)


def _semantic_search_fallback(subsystem, query: str) -> list[dict]:
    q = query.lower().strip()
    if not q:
        return []
    tokens = [t for t in re.split(r"\W+", q) if len(t) > 2]
    results = []

    def score_text(title: str, body: str = "") -> float:
        text = f"{title} {body}".lower()
        if q in text:
            return 1.0
        if not tokens:
            return 0.0
        hits = sum(1 for t in tokens if t in text)
        return hits / len(tokens)

    for case in CaseFile.objects.filter(subsystem=subsystem)[:300]:
        s = score_text(case.title, case.description or "")
        if s >= 0.34:
            results.append(
                {
                    "type": "case",
                    "id": case.pk,
                    "title": case.title,
                    "score": round(s, 2),
                }
            )
    for art in KnowledgeArticle.objects.filter(subsystem=subsystem):
        s = score_text(art.title, art.body or "")
        if s >= 0.34:
            results.append(
                {
                    "type": "knowledge",
                    "id": art.pk,
                    "title": art.title,
                    "score": round(s, 2),
                }
            )
    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:15]


def extract_entities(text: str) -> dict:
    emails = re.findall(r"[\w.-]+@[\w.-]+", text)
    phones = re.findall(r"\+?\d[\d\s()-]{8,}", text)
    return {"emails": emails[:5], "phones": phones[:5]}


def case_completeness(case: CaseFile) -> list[dict]:
    from delayu.services.document_completeness import casefile_completeness

    return casefile_completeness(case)


def predict_due_date(case: CaseFile) -> str:
    if case.due_date:
        return f"Текущий срок: {case.due_date.isoformat()}"
    return "По аналогам: +14 рабочих дней (демо M55)"


def sentiment(text: str) -> dict:
    t = text.lower()
    if any(w in t for w in ("жалоб", "возмущ", "безответствен")):
        return {"label": "Негативный", "score": 0.85, "escalate": True}
    if any(w in t for w in ("благодар", "доволен")):
        return {"label": "Позитивный", "score": 0.7, "escalate": False}
    return {"label": "Нейтральный", "score": 0.5, "escalate": False}


def suggest_bpm_step(case: CaseFile) -> str:
    pending = case.bpm_instances.filter(status="running").first()
    if pending:
        return f"Активен процесс «{pending.template.name}», шаг {pending.current_step_id or '—'}"
    return "Рекомендация: запустить шаблон «Согласование документа» (M60, демо)"


def autotag_document(title: str, description: str = "") -> list[str]:
    text = f"{title} {description}".lower()
    tags = []
    if "скан" in text or "pdf" in text:
        tags.append("скан")
    if "заяв" in text:
        tags.append("заявление")
    if "договор" in text:
        tags.append("договор")
    return tags or ["общий"]


def report_commentary(kpi: dict) -> str:
    return (
        f"За период: дел в работе {kpi.get('cases_open', 0)}, "
        f"просрочено {kpi.get('overdue', 0)}. "
        "Рекомендуется усилить контроль по просроченным (демо M65)."
    )


def qa_regulations(subsystem, question: str) -> str:
    for art in KnowledgeArticle.objects.filter(subsystem=subsystem, is_published=True):
        if question.lower() in art.body.lower()[:500] or question.lower() in art.title.lower():
            return f"По документу «{art.title}»: {art.body[:300]}…"
    return "Источник не найден в локальной базе НПА (демо M59)."


def ai_usage_today(subsystem):
    from django.utils import timezone

    from delayu.models import AiRequestLog

    today = timezone.now().date()
    return AiRequestLog.objects.filter(
        subsystem=subsystem, created_at__date=today
    ).count()


def get_or_create_policy(subsystem):
    from delayu.models import AiPolicy

    policy, _ = AiPolicy.objects.get_or_create(subsystem=subsystem)
    return policy


def is_ai_enabled(subsystem) -> bool:
    if not subsystem:
        return False
    return get_or_create_policy(subsystem).ai_enabled


def draft_appeal_response(appeal) -> dict:
    """Черновик ответа на обращение УЖВ (AI-P0-08, HITL)."""
    from delayu.models_uzhv import HousingAppeal

    cls = classify_correspondence(appeal.subject, appeal.body or "")
    citizen = appeal.citizen.full_name if appeal.citizen else "заявитель"
    case_ref = ""
    if appeal.housing_case_id:
        case_ref = f" Учётное дело {appeal.housing_case.case_number}."

    if cls["theme"] == "Жалоба":
        conclusion = HousingAppeal.ConclusionKind.INFO
        middle = (
            "Ваше обращение рассмотрено. По результатам проверки сообщаем следующее: "
            "информация по существу вопроса будет направлена дополнительно в установленный срок. "
            "Приносим извинения за доставленные неудобства."
        )
    elif cls["theme"] == "Малоимущие":
        conclusion = HousingAppeal.ConclusionKind.HOUSING
        middle = (
            "По вопросу признания (сохранения статуса) малоимущих сообщаем, что заявление "
            "принято к рассмотрению. Для принятия решения необходим полный пакет документов "
            "согласно перечню, установленному регламентом."
        )
    else:
        conclusion = HousingAppeal.ConclusionKind.INFO
        middle = (
            f"По сути обращения ({cls['theme'].lower()}) сообщаем, что сведения проверены. "
            "Ответ подготовлен на основании данных информационной системы УЖВ."
        )

    draft = (
        f"Уважаемый(ая) {citizen}!\n\n"
        f"На Ваше обращение № {appeal.appeal_number} от {appeal.received_at:%d.%m.%Y} "
        f"(срок ответа — до {appeal.due_date:%d.%m.%Y}){case_ref}\n\n"
        f"{middle}\n\n"
        "Данный текст сформирован автоматически и требует проверки специалистом "
        "перед регистрацией исходящего ответа.\n\n"
        "С уважением,\n"
        "Управление по жилищным вопросам"
    )
    return {
        "draft": draft,
        "conclusion_kind": conclusion,
        "classification": cls,
    }


def serialize_ai_policy(policy) -> dict:
    return {
        "model_name": policy.model_name,
        "max_requests_per_day": policy.max_requests_per_day,
        "allow_pii": policy.allow_pii,
        "ai_enabled": policy.ai_enabled,
        "notes": policy.notes,
    }


def update_ai_policy(policy, payload: dict) -> dict:
    fields = []
    if "model_name" in payload:
        policy.model_name = str(payload["model_name"])[:64]
        fields.append("model_name")
    if "max_requests_per_day" in payload:
        policy.max_requests_per_day = max(1, int(payload["max_requests_per_day"]))
        fields.append("max_requests_per_day")
    if "allow_pii" in payload:
        policy.allow_pii = bool(payload["allow_pii"])
        fields.append("allow_pii")
    if "ai_enabled" in payload:
        policy.ai_enabled = bool(payload["ai_enabled"])
        fields.append("ai_enabled")
    if "notes" in payload:
        policy.notes = str(payload["notes"])
        fields.append("notes")
    if fields:
        policy.save(update_fields=fields)
    return serialize_ai_policy(policy)


def _log(subsystem, user, module_code: str, prompt: str, response: str, *, meta: dict | None = None):
    """Запись в AiRequestLog (используется views_ai)."""
    AiRequestLog.objects.create(
        subsystem=subsystem,
        module_code=module_code,
        user=user,
        prompt=(prompt or "")[:8000],
        response=(response or "")[:8000],
        meta=meta or {},
    )
