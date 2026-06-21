"""M15–M21 — KPI, графики, качество, просрочки, аналитика по подразделениям."""
from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from delayu.models import (
    BPMTask,
    CaseFile,
    Correspondence,
    Department,
    DocumentFile,
    ReportTemplate,
    SLARule,
    TaskItem,
    UserAssignment,
)

REPORT_QUERY_KEYS = {
    "cases_summary": "Сводка по делам",
    "correspondence_in": "Входящая корреспонденция",
    "tasks_by_user": "Задачи по исполнителям",
    "docs_by_type": "Документы по типам",
    "bpm_pending": "Ожидающие согласования",
    "cases_trend": "Динамика дел за период",
}


def home_module_breakdown(subsystem):
    """
    Строки для блока «Сводка по направлениям» на главной (вместо демо Materio).
    """
    kpi = kpi_dashboard(subsystem)
    archived = CaseFile.objects.filter(subsystem=subsystem, is_archived=True).count()
    docs = DocumentFile.objects.filter(subsystem=subsystem, is_current=True).count()
    return [
        {
            "title": "Активные дела",
            "subtitle": "Картотека, не в архиве",
            "count": kpi["cases_total"],
            "badge": f'{kpi["cases_total"]} дел',
            "icon": "ri-folder-3-line",
            "color": "primary",
            "url_name": "platform-cases",
        },
        {
            "title": "В работе",
            "subtitle": "Статус «в исполнении»",
            "count": kpi["cases_in_progress"],
            "badge": f'{kpi["cases_in_progress"]} дел',
            "icon": "ri-briefcase-line",
            "color": "info",
            "url_name": "platform-cases",
        },
        {
            "title": "Просроченные дела",
            "subtitle": "Срок исполнения истёк",
            "count": kpi["cases_overdue"],
            "badge": f'{kpi["cases_overdue"]} дел',
            "icon": "ri-alarm-warning-line",
            "color": "danger",
            "url_name": "platform-cases",
        },
        {
            "title": "Входящая корреспонденция",
            "subtitle": "В работе по журналу",
            "count": kpi["corr_in_work"],
            "badge": f'{kpi["corr_in_work"]} писем',
            "icon": "ri-mail-line",
            "color": "warning",
            "url_name": "platform-inbox",
        },
        {
            "title": "Задачи",
            "subtitle": "Открытые поручения",
            "count": kpi["tasks_open"],
            "badge": f'{kpi["tasks_open"]} задач',
            "icon": "ri-checkbox-multiple-line",
            "color": "success",
            "url_name": "platform-kanban",
        },
        {
            "title": "Согласования БПМ",
            "subtitle": "Ожидают решения",
            "count": kpi["bpm_pending"],
            "badge": f'{kpi["bpm_pending"]} этапов',
            "icon": "ri-git-merge-line",
            "color": "secondary",
            "url_name": "platform-bpm-approvals",
        },
        {
            "title": "Документы",
            "subtitle": "Актуальные версии в делах",
            "count": docs,
            "badge": f"{docs} файлов",
            "icon": "ri-file-text-line",
            "color": "primary",
            "url_name": "platform-cases",
        },
        {
            "title": "Архив дел",
            "subtitle": "Закрытые и снятые с контроля",
            "count": archived,
            "badge": f"{archived} в архиве",
            "icon": "ri-archive-line",
            "color": "secondary",
            "url_name": "platform-archive-cases",
        },
    ]


def kpi_dashboard(subsystem):
    today = timezone.now().date()
    cases = CaseFile.objects.filter(subsystem=subsystem, is_archived=False)
    tasks = TaskItem.objects.filter(subsystem=subsystem, completed_at__isnull=True)
    corr_in = Correspondence.objects.filter(
        subsystem=subsystem, direction=Correspondence.Direction.IN
    )
    return {
        "cases_total": cases.count(),
        "cases_in_progress": cases.filter(status=CaseFile.Status.IN_PROGRESS).count(),
        "cases_overdue": cases.filter(due_date__lt=today)
        .exclude(status__in=[CaseFile.Status.DONE, CaseFile.Status.ARCHIVED])
        .count(),
        "tasks_open": tasks.count(),
        "tasks_overdue": tasks.filter(due_date__lt=today).count(),
        "corr_in_work": corr_in.filter(status=Correspondence.Status.IN_WORK).count(),
        "bpm_pending": BPMTask.objects.filter(
            instance__case__subsystem=subsystem, status=BPMTask.Status.PENDING
        ).count(),
        "cases_done": cases.filter(status=CaseFile.Status.DONE).count(),
        "by_status": list(
            cases.values("status").annotate(cnt=Count("id")).order_by("-cnt")
        ),
    }


def chart_cases_trend(subsystem, days=30):
    """Дела, созданные по дням (упрощённо — по updated_at)."""
    start = timezone.now().date() - timedelta(days=days)
    qs = (
        CaseFile.objects.filter(subsystem=subsystem, created_at__date__gte=start)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(cnt=Count("id"))
        .order_by("day")
    )
    labels = []
    series = []
    for row in qs:
        labels.append(row["day"].isoformat() if row["day"] else "")
        series.append(row["cnt"])
    return {"labels": labels, "series": series, "title": "Новые дела за период"}


_PRIORITY_LABELS = {1: "Низкий", 2: "Средний", 3: "Высокий", 4: "Критичный"}


def chart_tasks_by_priority(subsystem):
    rows = (
        TaskItem.objects.filter(subsystem=subsystem, completed_at__isnull=True)
        .values("priority")
        .annotate(cnt=Count("id"))
        .order_by("priority")
    )
    labels = [
        _PRIORITY_LABELS.get(int(r["priority"]), f"Приоритет {r['priority']}") for r in rows
    ]
    series = [r["cnt"] for r in rows]
    return {"labels": labels, "series": series, "title": "Открытые задачи по приоритету"}


def chart_cases_by_status(subsystem):
    """Дела по статусам для горизонтальной диаграммы."""
    kpi = kpi_dashboard(subsystem)
    status_map = dict(CaseFile.Status.choices)
    labels = []
    series = []
    for row in kpi["by_status"]:
        labels.append(status_map.get(row["status"], row["status"]))
        series.append(row["cnt"])
    return {"labels": labels, "series": series, "title": "Дела по статусам"}


def home_queue_tabs(subsystem) -> list:
    """Строки для вкладок таблицы на главной (дела / корреспонденция / задачи / БПМ)."""
    status_badge = {
        CaseFile.Status.NEW: "info",
        CaseFile.Status.IN_PROGRESS: "primary",
        CaseFile.Status.WAITING: "warning",
        CaseFile.Status.DONE: "success",
        CaseFile.Status.ARCHIVED: "secondary",
    }
    tabs = []

    case_rows = []
    for c in (
        CaseFile.objects.filter(subsystem=subsystem, is_archived=False)
        .select_related("assignee")
        .order_by("-updated_at")[:5]
    ):
        case_rows.append(
            {
                "title": f"{c.number} — {c.title[:50]}",
                "status": c.get_status_display(),
                "status_class": status_badge.get(c.status, "secondary"),
                "col3": c.due_date.strftime("%d.%m.%Y") if c.due_date else "—",
                "col4": (c.assignee.get_full_name() or c.assignee.username) if c.assignee else "—",
            }
        )
    tabs.append(
        {
            "tab_id": "navs-orders-id",
            "icon": "ri-folder-3-line",
            "color": "primary",
            "label": "Дела",
            "rows": case_rows,
        }
    )

    corr_rows = []
    for cr in (
        Correspondence.objects.filter(subsystem=subsystem)
        .select_related("assignee")
        .order_by("-reg_date", "-created_at")[:5]
    ):
        corr_rows.append(
            {
                "title": f"{cr.reg_number} — {(cr.subject or '')[:45]}",
                "status": cr.get_status_display(),
                "status_class": "warning",
                "col3": cr.reg_date.strftime("%d.%m.%Y") if cr.reg_date else "—",
                "col4": (cr.assignee.get_full_name() or cr.assignee.username) if cr.assignee else "—",
            }
        )
    tabs.append(
        {
            "tab_id": "navs-sales-id",
            "icon": "ri-mail-line",
            "color": "info",
            "label": "Корреспонденция",
            "rows": corr_rows,
        }
    )

    task_rows = []
    for t in (
        TaskItem.objects.filter(subsystem=subsystem, completed_at__isnull=True)
        .select_related("assignee")
        .order_by("-due_date", "-created_at")[:5]
    ):
        task_rows.append(
            {
                "title": t.title[:60],
                "status": "Открыта",
                "status_class": "primary",
                "col3": f"П{t.priority}",
                "col4": (t.assignee.get_full_name() or t.assignee.username) if t.assignee else "—",
            }
        )
    tabs.append(
        {
            "tab_id": "navs-profit-id",
            "icon": "ri-checkbox-multiple-line",
            "color": "success",
            "label": "Задачи",
            "rows": task_rows,
        }
    )

    bpm_rows = []
    for bt in (
        BPMTask.objects.filter(
            instance__case__subsystem=subsystem, status=BPMTask.Status.PENDING
        )
        .select_related("instance", "instance__case")
        .order_by("instance__started_at", "id")[:5]
    ):
        case = bt.instance.case if bt.instance_id else None
        bpm_rows.append(
            {
                "title": (bt.step_name or "Согласование")[:60],
                "status": "Ожидает",
                "status_class": "warning",
                "col3": case.number if case else "—",
                "col4": case.title[:30] if case else "—",
            }
        )
    tabs.append(
        {
            "tab_id": "navs-income-id",
            "icon": "ri-git-merge-line",
            "color": "secondary",
            "label": "БПМ",
            "rows": bpm_rows,
        }
    )

    return tabs


def home_weekly_summary(subsystem) -> dict:
    kpi = kpi_dashboard(subsystem)
    trend = chart_cases_trend(subsystem, days=7)
    return {
        "new_cases_week": sum(trend.get("series", [])),
        "overdue_cases": kpi.get("cases_overdue", 0),
    }


def chart_tasks_by_user(subsystem, *, limit: int = 8) -> dict:
    """Открытые задачи по исполнителям — горизонтальная диаграмма на главной."""
    rows = (
        TaskItem.objects.filter(subsystem=subsystem, completed_at__isnull=True)
        .values(
            "assignee_id",
            "assignee__username",
            "assignee__first_name",
            "assignee__last_name",
        )
        .annotate(cnt=Count("id"))
        .order_by("-cnt")[:limit]
    )
    labels = []
    series = []
    for row in rows:
        fn = (row.get("assignee__first_name") or "").strip()
        ln = (row.get("assignee__last_name") or "").strip()
        name = f"{fn} {ln}".strip() or row.get("assignee__username") or "Без исполнителя"
        labels.append(name[:24])
        series.append(row["cnt"])
    return {"labels": labels, "series": series, "title": "Задачи по исполнителям"}


def chart_load_radar(subsystem) -> dict:
    """Нагрузка по направлениям — radar на главной."""
    kpi = kpi_dashboard(subsystem)
    return {
        "categories": ["Дела", "В работе", "Задачи", "Вх. письма", "БПМ", "Просроч."],
        "series": [
            {
                "name": "Нагрузка",
                "data": [
                    kpi["cases_total"],
                    kpi["cases_in_progress"],
                    kpi["tasks_open"],
                    kpi["corr_in_work"],
                    kpi["bpm_pending"],
                    kpi["cases_overdue"],
                ],
            }
        ],
    }


def home_dashboard_payload(subsystem, *, days: int = 30) -> dict:
    """JSON для графиков главной страницы (см. delayu-dashboard-analytics.js)."""
    kpi = kpi_dashboard(subsystem)
    total = kpi["cases_total"] or 0
    completion = round(100 * kpi["cases_done"] / total) if total else 0
    return {
        "kpi": kpi,
        "completion_pct": completion,
        "cases_trend": chart_cases_trend(subsystem, days=days),
        "tasks_priority": chart_tasks_by_priority(subsystem),
        "status_chart": chart_cases_by_status(subsystem),
        "tasks_by_user": chart_tasks_by_user(subsystem),
        "radar_load": chart_load_radar(subsystem),
        "load_by_user": run_report_query(subsystem, "tasks_by_user").get("rows", []),
    }


def chart_correspondence_status(subsystem):
    rows = (
        Correspondence.objects.filter(subsystem=subsystem)
        .values("status")
        .annotate(cnt=Count("id"))
    )
    return {
        "labels": [r["status"] for r in rows],
        "series": [r["cnt"] for r in rows],
        "title": "Корреспонденция по статусам",
    }


def quality_metrics(subsystem):
    today = timezone.now().date()
    cases = CaseFile.objects.filter(subsystem=subsystem, is_archived=False)
    corr = Correspondence.objects.filter(subsystem=subsystem)
    docs = DocumentFile.objects.filter(subsystem=subsystem, is_current=True)
    total_cases = cases.count() or 1
    without_assignee = cases.filter(assignee__isnull=True).count()
    corr_no_case = corr.filter(case__isnull=True).count()
    unsigned_docs = docs.filter(is_signed=False).count()
    overdue = cases.filter(due_date__lt=today).exclude(
        status__in=[CaseFile.Status.DONE, CaseFile.Status.ARCHIVED]
    ).count()
    sla_rule = SLARule.objects.filter(subsystem=subsystem).first()
    sla_hours = sla_rule.hours_limit if sla_rule else 72
    return {
        "assignee_fill_pct": round(100 * (total_cases - without_assignee) / total_cases, 1),
        "without_assignee": without_assignee,
        "corr_no_case": corr_no_case,
        "unsigned_docs": unsigned_docs,
        "overdue_cases": overdue,
        "sla_hours": sla_hours,
        "sla_risk_pct": round(100 * overdue / total_cases, 1) if total_cases else 0,
        "repeat_corr": corr.filter(subject__icontains="повтор").count(),
    }


def overdue_monitor(subsystem, *, risk_days=3):
    today = timezone.now().date()
    risk_until = today + timedelta(days=risk_days)
    items = []

    def _light(due):
        if not due:
            return "green", "Без срока"
        if due < today:
            return "red", "Просрочено"
        if due <= risk_until:
            return "yellow", "Скоро срок"
        return "green", "В норме"

    for c in CaseFile.objects.filter(subsystem=subsystem, is_archived=False).exclude(
        status=CaseFile.Status.DONE
    ).select_related("assignee")[:80]:
        light, label = _light(c.due_date)
        items.append(
            {
                "kind": "Дело",
                "ref": c.number,
                "title": c.title[:80],
                "due": c.due_date,
                "assignee": c.assignee,
                "light": light,
                "light_label": label,
                "url": f"/cases/{c.pk}/",
            }
        )
    for t in TaskItem.objects.filter(
        subsystem=subsystem, completed_at__isnull=True
    ).select_related("assignee")[:40]:
        light, label = _light(t.due_date)
        items.append(
            {
                "kind": "Задача",
                "ref": f"#{t.pk}",
                "title": t.title[:80],
                "due": t.due_date,
                "assignee": t.assignee,
                "light": light,
                "light_label": label,
                "url": f"/workspace/tasks/{t.pk}/",
            }
        )
    order = {"red": 0, "yellow": 1, "green": 2}
    items.sort(key=lambda x: (order.get(x["light"], 9), x["due"] or today))
    return items


def department_analytics(subsystem, organization):
    rows = []
    depts = Department.objects.filter(organization=organization).select_related("manager")
    for dept in depts:
        user_ids = list(
            UserAssignment.objects.filter(department=dept).values_list("user_id", flat=True)
        )
        if not user_ids:
            user_ids = [-1]
        today = timezone.now().date()
        cases_qs = CaseFile.objects.filter(
            subsystem=subsystem, assignee_id__in=user_ids, is_archived=False
        )
        open_cnt = cases_qs.count()
        overdue = cases_qs.filter(due_date__lt=today).exclude(
            status=CaseFile.Status.DONE
        ).count()
        done = CaseFile.objects.filter(
            subsystem=subsystem, assignee_id__in=user_ids, status=CaseFile.Status.DONE
        ).count()
        score = 100
        if open_cnt:
            score = max(0, round(100 - 100 * overdue / open_cnt))
        rows.append(
            {
                "department": dept,
                "open_cases": open_cnt,
                "overdue": overdue,
                "done": done,
                "score": score,
            }
        )
    rows.sort(key=lambda r: -r["score"])
    return rows


def run_report_query(subsystem, query_key: str, *, period_days=30) -> dict:
    """Расширенный запуск отчёта для M16."""
    from delayu.services import reports

    if query_key == "cases_trend":
        ch = chart_cases_trend(subsystem, days=period_days)
        return {
            "chart": ch,
            "columns": ["day", "cnt"],
            "rows": [{"day": l, "cnt": s} for l, s in zip(ch["labels"], ch["series"])],
            "title": ch["title"],
        }
    base = reports.run_report(subsystem, query_key)
    if base.get("message") and not base.get("rows"):
        return base
    tpl = ReportTemplate.objects.filter(subsystem=subsystem, query_key=query_key).first()
    title = tpl.name if tpl else REPORT_QUERY_KEYS.get(query_key, query_key)
    columns = list(base["rows"][0].keys()) if base.get("rows") else []
    return {**base, "columns": columns, "title": title}
