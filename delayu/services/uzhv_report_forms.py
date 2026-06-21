"""Эталонные формы ОТЧ-6 и ОТЧ-9 (Приложение по формам АИС УЖВ)."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.db.models import Count, Q
from django.utils import timezone

from delayu.models_uzhv import HousingContract, MunicipalBuilding, MunicipalPremise

_FORMS_DIR = Path(__file__).resolve().parents[2] / "docs" / "uzv" / "form"

OTCH6_HEADER = [
    "№ п/п",
    "Адрес МКД",
    "№ помещения",
    "Общая площадь, м²",
    "Число комнат",
    "Состояние на начало периода",
    "Поступило за период",
    "Выбыло за период",
    "Состояние на конец периода",
    "№ договора",
    "Ф.И.О. нанимателя",
    "Дата договора / расторжения",
    "Вид договора",
    "Примечание",
]

OTCH9_HEADER = [
    "№ п/п",
    "Адрес МКД",
    "Кадастровый номер",
    "Год постройки",
    "Этажность",
    "Общая площадь МКД, м²",
    "Число жилых помещений",
    "Численность проживающих",
    "Состояние МКД",
    "Включён в программу № 4779",
    "Статус расселения",
    "Примечание",
]

FORM_REPORT_CODES = frozenset({"otch-6", "otch-9"})


def _load_header(code: str) -> list[str]:
    path = _FORMS_DIR / f"{code}-columns.json"
    if path.is_file():
        text = path.read_text(encoding="utf-8")
        lines = [ln for ln in text.splitlines() if not ln.strip().startswith("#")]
        data = json.loads("\n".join(lines))
        return data.get("header_row", [])
    return OTCH6_HEADER if code == "otch-6" else OTCH9_HEADER


def _active_contract(premise: MunicipalPremise, on_date: date) -> HousingContract | None:
    qs = premise.contracts.filter(signed_at__lte=on_date).filter(
        Q(terminated_at__isnull=True) | Q(terminated_at__gt=on_date)
    ).filter(Q(valid_until__isnull=True) | Q(valid_until__gte=on_date))
    return qs.select_related("citizen").order_by("-signed_at").first()


def _occupancy_label(premise: MunicipalPremise, on_date: date) -> str:
    c = _active_contract(premise, on_date)
    if c:
        return "Занято"
    if premise.status == MunicipalPremise.Status.OCCUPIED:
        return "Занято"
    if premise.status == MunicipalPremise.Status.RESERVED:
        return "Резерв"
    return "Свободно"


def _decimal_sum(values) -> Decimal:
    total = Decimal("0")
    for v in values:
        if v is not None and v != "":
            try:
                total += Decimal(str(v))
            except Exception:
                pass
    return total


def build_otch6_rows(
    subsystem,
    period_start: date | None,
    period_end: date | None,
) -> tuple[str, list[list]]:
    """ОТЧ-6 — движение жилфонда за период (форма приложения ТЗ)."""
    period_end = period_end or timezone.now().date()
    period_start = period_start or date(period_end.year, ((period_end.month - 1) // 3) * 3 + 1, 1)
    ps = period_start.strftime("%d.%m.%Y")
    pe = period_end.strftime("%d.%m.%Y")
    today = timezone.now().strftime("%d.%m.%Y")
    title = "ОТЧ-6 — Движение жилищного фонда"
    header = _load_header("otch-6") or OTCH6_HEADER

    rows: list[list] = [
        [title],
        [f"Подсистема: {subsystem.name}"],
        [f"Отчётный период: с {ps} по {pe}"],
        [f"Дата формирования: {today}"],
        [],
        header,
    ]

    qs = (
        MunicipalPremise.objects.filter(building__subsystem=subsystem)
        .select_related("building")
        .prefetch_related("contracts__citizen")
        .order_by("building__address", "number")
    )

    received_total = 0
    disposed_total = 0
    areas = []

    for i, p in enumerate(qs, 1):
        c_end = _active_contract(p, period_end)
        signed = p.contracts.filter(
            signed_at__gt=period_start, signed_at__lte=period_end
        ).order_by("-signed_at")
        terminated = p.contracts.filter(
            terminated_at__gt=period_start, terminated_at__lte=period_end
        ).order_by("-terminated_at")
        received = signed.count()
        disposed = terminated.count()
        received_total += received
        disposed_total += disposed
        if p.area_sqm:
            areas.append(p.area_sqm)

        ref = c_end or signed.first() or terminated.first()
        contract_no = ref.contract_number if ref else ""
        tenant = ref.citizen.full_name if ref else ""
        if terminated.first() and not c_end:
            ref = terminated.first()
            contract_no = ref.contract_number
            tenant = ref.citizen.full_name
            date_ref = ref.terminated_at.strftime("%d.%m.%Y") if ref.terminated_at else ""
            note = ref.termination_reason or ""
        elif ref:
            date_ref = ref.signed_at.strftime("%d.%m.%Y")
            note = ref.notes[:120] if ref.notes else ""
        else:
            date_ref = ""
            note = ""

        rows.append(
            [
                i,
                p.building.address,
                p.number,
                p.area_sqm or "",
                p.rooms or "",
                _occupancy_label(p, period_start),
                received or "",
                disposed or "",
                _occupancy_label(p, period_end),
                contract_no,
                tenant,
                date_ref,
                ref.get_contract_type_display() if ref else "",
                note,
            ]
        )

    rows.extend(
        [
            [],
            ["Сводка за период", "", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["Всего помещений", qs.count(), "", "", "", "", "", "", "", "", "", "", "", ""],
            ["Суммарная площадь, м²", str(_decimal_sum(areas)), "", "", "", "", "", "", "", "", "", "", "", ""],
            ["Поступило (договоров заключено)", received_total, "", "", "", "", "", "", "", "", "", "", "", ""],
            ["Выбыло (договоров расторгнуто)", disposed_total, "", "", "", "", "", "", "", "", "", "", "", ""],
        ]
    )
    return title, rows


def _resettlement_status(building: MunicipalBuilding) -> str:
    if building.condition == MunicipalBuilding.Condition.OK and not building.in_resettlement_program:
        if building.notes and "рассел" in building.notes.lower():
            return "Расселён"
        return "—"
    if building.condition == MunicipalBuilding.Condition.RENOVATION:
        return "В процессе расселения"
    if building.condition == MunicipalBuilding.Condition.EMERGENCY:
        return "Не расселён"
    if building.in_resettlement_program:
        return "В программе"
    return "—"


def build_otch9_rows(
    subsystem,
    period_start: date | None = None,
    period_end: date | None = None,
) -> tuple[str, list[list]]:
    """ОТЧ-9 — сводка по программе расселения аварийного фонда (4779)."""
    today = timezone.now().strftime("%d.%m.%Y")
    title = "ОТЧ-9 — Переселение аварийного жилого фонда"
    header = _load_header("otch-9") or OTCH9_HEADER

    rows: list[list] = [
        [title],
        [f"Подсистема: {subsystem.name}"],
        ["Муниципальная программа № 4779 «Расселение аварийного фонда»"],
        [f"Дата формирования: {today}"],
        [],
        header,
    ]

    qs = (
        MunicipalBuilding.objects.filter(subsystem=subsystem)
        .filter(
            Q(in_resettlement_program=True)
            | Q(condition=MunicipalBuilding.Condition.EMERGENCY)
            | Q(condition=MunicipalBuilding.Condition.RENOVATION)
        )
        .annotate(premise_count=Count("premises"))
        .order_by("address")
    )

    for i, b in enumerate(qs, 1):
        rows.append(
            [
                i,
                b.address,
                b.cadastral_number or "",
                b.year_built or "",
                b.floors or "",
                b.total_area_sqm or "",
                b.premise_count,
                b.residents_count or "",
                b.get_condition_display(),
                "Да" if b.in_resettlement_program else "Нет",
                _resettlement_status(b),
                (b.notes[:200] if b.notes else ""),
            ]
        )

    rows.extend(
        [
            [],
            ["Итого объектов", qs.count(), "", "", "", "", "", "", "", "", "", ""],
            [
                "Суммарная площадь, м²",
                str(_decimal_sum(b.total_area_sqm for b in qs)),
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "Суммарно жителей",
                sum(b.residents_count or 0 for b in qs),
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ],
        ]
    )
    return title, rows


def build_form_report_rows(
    code: str,
    subsystem,
    period_start: date | None = None,
    period_end: date | None = None,
) -> tuple[str, list[list]]:
    if code == "otch-6":
        return build_otch6_rows(subsystem, period_start, period_end)
    if code == "otch-9":
        return build_otch9_rows(subsystem, period_start, period_end)
    raise KeyError(code)
