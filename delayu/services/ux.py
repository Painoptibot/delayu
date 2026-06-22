"""M83–M86 — лицензии, обучение, дашборды, marketplace."""
from datetime import date

from django.db.models import Q

from delayu.models import (
    LicenseEntitlement,
    MarketplaceConnector,
    OnboardingArticle,
    SubsystemModule,
    UserDashboardLayout,
)


from delayu.services import studio


def ux_hub_metrics(subsystem):
    today = date.today()
    expiring = LicenseEntitlement.objects.filter(
        subsystem=subsystem, valid_until__isnull=False, valid_until__lte=today
    ).count()
    return {
        "licenses": LicenseEntitlement.objects.filter(subsystem=subsystem).count(),
        "licenses_expiring": expiring,
        "onboarding": OnboardingArticle.objects.filter(
            Q(subsystem=subsystem) | Q(subsystem__isnull=True), is_published=True
        ).count(),
        "connectors": MarketplaceConnector.objects.count(),
    }


def license_rows(subsystem):
    enabled = {
        link.module_id: link.enabled
        for link in SubsystemModule.objects.filter(subsystem=subsystem).select_related("module")
    }
    rows = []
    for ent in LicenseEntitlement.objects.filter(subsystem=subsystem).select_related("module"):
        rows.append(
            {
                "entitlement": ent,
                "enabled": enabled.get(ent.module_id, False),
                "expired": ent.valid_until and ent.valid_until < date.today(),
            }
        )
    return rows


def filter_onboarding(subsystem, params=None):
    params = params or {}
    qs = OnboardingArticle.objects.filter(Q(subsystem=subsystem) | Q(subsystem__isnull=True))
    kind = (params.get("kind") or "").strip()
    if kind:
        qs = qs.filter(kind=kind)
    if params.get("published") == "1":
        qs = qs.filter(is_published=True)
    return qs.order_by("sort_order", "title")


def filter_dashboard_layouts(user, subsystem):
    return UserDashboardLayout.objects.filter(user=user, subsystem=subsystem).order_by(
        "-is_default", "name"
    )


def default_widgets():
    return [
        {"id": "overview", "title": "Сводка", "col": 12},
        {"id": "kpi_row", "title": "KPI", "col": 12},
        {"id": "kpi_cases", "title": "Дела", "col": 6},
        {"id": "kpi_tasks", "title": "Задачи", "col": 6},
        {"id": "kpi_overdue", "title": "Просрочки", "col": 6},
        {"id": "kpi_bpm", "title": "BPM", "col": 6},
        {"id": "chart_radar", "title": "Радар", "col": 4},
        {"id": "chart_sessions", "title": "Тренд", "col": 4},
        {"id": "chart_load", "title": "Нагрузка", "col": 4},
        {"id": "chart_volume", "title": "Объём", "col": 4},
        {"id": "chart_status", "title": "Статусы", "col": 8},
        {"id": "chart_weekly", "title": "Динамика", "col": 8},
        {"id": "chart_priority", "title": "Приоритеты", "col": 4},
        {"id": "list_overdue", "title": "Просроченные", "col": 6},
        {"id": "quick_links", "title": "Ссылки", "col": 6},
    ]


def get_dashboard_layout(user, subsystem):
    layout = UserDashboardLayout.objects.filter(
        user=user, subsystem=subsystem, is_default=True
    ).first()
    if not layout:
        layout = (
            UserDashboardLayout.objects.filter(user=user, subsystem=subsystem)
            .order_by("-updated_at")
            .first()
        )
    return layout


def dashboard_widgets_for_user(user, subsystem) -> list:
    from delayu.models import SubsystemMembership, RoleStudioLayout

    membership = (
        SubsystemMembership.objects.filter(user=user, subsystem=subsystem)
        .select_related("role")
        .first()
    )
    if membership and membership.role_id:
        raw = RoleStudioLayout.objects.filter(
            subsystem=subsystem,
            role=membership.role,
            kind=RoleStudioLayout.Kind.DASHBOARD,
        ).first()
        if raw and raw.widgets:
            return studio.normalize_dashboard_widgets(raw.widgets)

    layout = get_dashboard_layout(user, subsystem)
    if layout and layout.widgets:
        return studio.normalize_dashboard_widgets(layout.widgets)
    return default_widgets()


def filter_marketplace(params=None):
    params = params or {}
    qs = MarketplaceConnector.objects.all()
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(vendor__icontains=q) | Q(code__icontains=q))
    if params.get("certified") == "1":
        qs = qs.filter(is_certified=True)
    return qs.order_by("-is_certified", "name")
