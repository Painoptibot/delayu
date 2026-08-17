"""Deterministic mock fixtures keyed by INN / cadastral."""
from __future__ import annotations

from typing import Any

# Special INNs used in tests / demos
HARD_BANKRUPT_INN = "7707083893"  # valid checksum; mock = bankrupt
CLEAN_INN = "500100732259"  # valid 12-digit IP-like; mock = clean
WARN_INN = "7736050003"  # valid; mock = FSSP warn


def fixture_for_inn(inn: str) -> dict[str, Any]:
    inn = "".join(ch for ch in (inn or "") if ch.isdigit())
    if inn == HARD_BANKRUPT_INN:
        return {
            "profile": "bankrupt",
            "name": "ООО Тест Банкрот",
            "ogrn": "1027700132195",
            "status": "в процессе банкротства",
            "active": False,
            "bankrupt": True,
            "fssp_count": 2,
            "kad_count": 5,
            "rnp": False,
            "disqualified": False,
            "bfo_years": [],
            "pb_risks": ["банкротство"],
        }
    if inn == WARN_INN:
        return {
            "profile": "warn",
            "name": "АО Предупреждение",
            "ogrn": "1027739000000",
            "status": "действующее",
            "active": True,
            "bankrupt": False,
            "fssp_count": 3,
            "kad_count": 1,
            "rnp": False,
            "disqualified": False,
            "bfo_years": [2023, 2024],
            "pb_risks": ["исполнительные производства"],
        }
    if not inn:
        return {
            "profile": "empty",
            "name": "",
            "ogrn": "",
            "status": "",
            "active": False,
            "bankrupt": False,
            "fssp_count": 0,
            "kad_count": 0,
            "rnp": False,
            "disqualified": False,
            "bfo_years": [],
            "pb_risks": [],
        }
    return {
        "profile": "clean",
        "name": "ООО Чистый Инвестор",
        "ogrn": "1027700000000",
        "status": "действующее",
        "active": True,
        "bankrupt": False,
        "fssp_count": 0,
        "kad_count": 0,
        "rnp": False,
        "disqualified": False,
        "bfo_years": [2022, 2023, 2024],
        "pb_risks": [],
    }


def fixture_for_cadastral(cadastral: str) -> dict[str, Any]:
    kn = (cadastral or "").strip()
    if not kn:
        return {"found": False, "nspd": False, "fgistp_docs": 0, "mnp_hard": 0, "mnp_zones": 0}
    if "9999" in kn:
        return {"found": False, "nspd": False, "fgistp_docs": 0, "mnp_hard": 0, "mnp_zones": 0}
    return {
        "found": True,
        "nspd": True,
        "address": "Краснодарский край, демо-адрес",
        "area_ha": 1.25,
        "fgistp_docs": 2,
        "mnp_hard": 0,
        "mnp_zones": 3,
    }
