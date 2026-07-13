"""Остатки топлива по видам на АЗС."""
from __future__ import annotations

from delayu.models_fuel import FuelAzsStation

AZS_FUEL_KINDS: tuple[dict[str, str], ...] = (
    {"code": "ai92", "label": "АИ-92", "stock": "stock_ai92_liters", "sells": "sells_ai92"},
    {"code": "ai95", "label": "АИ-95", "stock": "stock_ai95_liters", "sells": "sells_ai95"},
    {"code": "diesel", "label": "Дизель", "stock": "stock_diesel_liters", "sells": "sells_diesel"},
    {"code": "gas", "label": "Газ (СУГ)", "stock": "stock_gas_liters", "sells": "sells_gas"},
)


def azs_fuel_stock_rows(azs: FuelAzsStation) -> list[dict]:
    rows = []
    for kind in AZS_FUEL_KINDS:
        sells = bool(getattr(azs, kind["sells"]))
        liters = int(getattr(azs, kind["stock"]) or 0)
        rows.append(
            {
                "code": kind["code"],
                "label": kind["label"],
                "liters": liters,
                "sells": sells,
                "available": sells and liters > 0,
            }
        )
    return rows


def azs_fuel_stock_summary(azs: FuelAzsStation) -> str:
    parts = []
    for row in azs_fuel_stock_rows(azs):
        if not row["sells"]:
            continue
        if row["liters"] > 0:
            parts.append(f"{row['label']}: {row['liters']} л")
        else:
            parts.append(f"{row['label']}: нет")
    return " · ".join(parts) if parts else "—"


def azs_gasoline_liters(azs: FuelAzsStation) -> int:
    return max(0, int(azs.stock_ai92_liters or 0) + int(azs.stock_ai95_liters or 0))


def recompute_azs_primary_grade(azs: FuelAzsStation) -> None:
    if int(azs.stock_ai95_liters or 0) >= int(azs.stock_ai92_liters or 0) and int(
        azs.stock_ai95_liters or 0
    ) > 0:
        azs.fuel_grade = "АИ-95"
    elif int(azs.stock_ai92_liters or 0) > 0:
        azs.fuel_grade = "АИ-92"
    elif int(azs.stock_diesel_liters or 0) > 0:
        azs.fuel_grade = "Дизель"


def apply_azs_fuel_stock(
    azs: FuelAzsStation,
    *,
    stock_ai92_liters: int | None = None,
    stock_ai95_liters: int | None = None,
    stock_diesel_liters: int | None = None,
    stock_gas_liters: int | None = None,
    sells_ai92: bool | None = None,
    sells_ai95: bool | None = None,
    sells_diesel: bool | None = None,
    sells_gas: bool | None = None,
) -> FuelAzsStation:
    if stock_ai92_liters is not None:
        azs.stock_ai92_liters = max(0, int(stock_ai92_liters))
    if stock_ai95_liters is not None:
        azs.stock_ai95_liters = max(0, int(stock_ai95_liters))
    if stock_diesel_liters is not None:
        azs.stock_diesel_liters = max(0, int(stock_diesel_liters))
    if stock_gas_liters is not None:
        azs.stock_gas_liters = max(0, int(stock_gas_liters))
    if sells_ai92 is not None:
        azs.sells_ai92 = bool(sells_ai92)
    if sells_ai95 is not None:
        azs.sells_ai95 = bool(sells_ai95)
    if sells_diesel is not None:
        azs.sells_diesel = bool(sells_diesel)
    if sells_gas is not None:
        azs.sells_gas = bool(sells_gas)

    azs.stock_liters = azs_gasoline_liters(azs)
    recompute_azs_primary_grade(azs)

    gasoline = azs.stock_liters
    if gasoline == 0:
        azs.status = FuelAzsStation.Status.EMPTY
        azs.is_accepting_permits = False
    elif gasoline < 1000:
        if azs.status != FuelAzsStation.Status.BUSY:
            azs.status = FuelAzsStation.Status.LOW
    elif azs.status in (FuelAzsStation.Status.EMPTY, FuelAzsStation.Status.LOW):
        azs.status = FuelAzsStation.Status.OK
        azs.is_accepting_permits = True
    return azs


def serialize_azs_fuel_stock(azs: FuelAzsStation) -> dict:
    return {
        "summary": azs_fuel_stock_summary(azs),
        "gasoline_liters": azs_gasoline_liters(azs),
        "items": azs_fuel_stock_rows(azs),
    }
