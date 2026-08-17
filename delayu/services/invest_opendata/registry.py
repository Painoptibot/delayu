"""Register P0 open-data adapters."""
from __future__ import annotations

from delayu.services.invest_opendata.adapters_kyc import KYC_ADAPTERS
from delayu.services.invest_opendata.adapters_site import SITE_ADAPTERS
from delayu.services.invest_opendata.base import EntityKind

SOURCE_DESCRIPTIONS = {
    "egrul_fns": "Статус юрлица, наименование, ОГРН, действующее/нет",
    "transparent_business": "Риски ФНС «Прозрачный бизнес»",
    "bfo_nalog": "Наличие бухгалтерской отчётности (БФО)",
    "fedresurs": "Банкротство / сообщения ЕФРСБ",
    "fssp": "Исполнительные производства",
    "kad_arbitr": "Арбитражные дела (КАД)",
    "eis_rnp": "Реестр недобросовестных поставщиков (ЕИС)",
    "disqualified": "Дисквалификация руководителей",
    "nspd_public": "Публичные сведения ЗУ в НСПД",
    "fgistp_public": "Документы территориального планирования",
    "mnp_local": "Пересечения с локальным store генплана МНП",
}

SOURCE_PORTALS = {
    "egrul_fns": "https://egrul.nalog.ru/",
    "transparent_business": "https://pb.nalog.gov.ru/",
    "bfo_nalog": "https://bo.nalog.gov.ru/",
    "fedresurs": "https://bankrot.fedresurs.ru/",
    "fssp": "https://fssp.gov.ru/iss/ip/",
    "kad_arbitr": "https://kad.arbitr.ru/",
    "eis_rnp": "https://zakupki.gov.ru/",
    "disqualified": "https://www.nalog.gov.ru/rn77/related_activities/registries/disqualified_persons/",
    "nspd_public": "https://nspd.gov.ru/",
    "fgistp_public": "https://fgistp.economy.gov.ru/",
    "mnp_local": "",
}


def all_adapters():
    return list(KYC_ADAPTERS) + list(SITE_ADAPTERS)


def adapters_for(kind: EntityKind):
    return [a for a in all_adapters() if kind in a.entity_kinds]


def catalog_rows() -> list[dict]:
    rows = []
    for adapter in all_adapters():
        rows.append(
            {
                "code": adapter.code,
                "label": adapter.label,
                "entity_kinds": list(adapter.entity_kinds),
                "description": SOURCE_DESCRIPTIONS.get(adapter.code, ""),
                "portal_url": SOURCE_PORTALS.get(adapter.code, ""),
            }
        )
    return rows
