"""Матрица опций I-01…I-14 из ТЗ УЖВ и их замена на этапе 1 (без СМЭВ/ГИС)."""


def tz_integration_options() -> list[dict]:
    """
    Статусы: stage2 | partial | done | manual | scripts
    """
    return [
        {
            "code": "I-01",
            "name": "ГИС ЖКХ",
            "tz_status": "stage2",
            "stage1": "Импорт CSV/XLSX (PY-01), ручной ввод МКД",
            "endpoint": "",
        },
        {
            "code": "I-02",
            "name": "АИС «Жилье»",
            "tz_status": "stage2",
            "stage1": "Ручной учёт проверок и предписаний",
            "endpoint": "",
        },
        {
            "code": "I-03",
            "name": "ФРТ (аварийное жильё)",
            "tz_status": "stage2",
            "stage1": "Поля расселения в карточке МКД",
            "endpoint": "",
        },
        {
            "code": "I-04",
            "name": "Минтруд КК (дети-сироты)",
            "tz_status": "manual",
            "stage1": "Реестр /uzhv/orphans/, решения вручную",
            "endpoint": "",
        },
        {
            "code": "I-05",
            "name": "ЕПГУ / Госуслуги",
            "tz_status": "partial",
            "stage1": "Входящий API + публичная форма",
            "endpoint": "epgu_uzhv, /public/…/appeal/",
        },
        {
            "code": "I-06",
            "name": "Уведомления ЕПГУ",
            "tz_status": "partial",
            "stage1": "M78 + PY-07 (JSON для внешней отправки)",
            "endpoint": "uzhv_py07_notify_payload",
        },
        {
            "code": "I-07",
            "name": "МФЦ",
            "tz_status": "partial",
            "stage1": "Входящий API (тот же формат, что ЕПГУ)",
            "endpoint": "mfc_uzhv",
        },
        {
            "code": "I-08",
            "name": "Катарсис / СМЭВ",
            "tz_status": "stage2",
            "stage1": "Межвед. запросы вручную, канал smev не активен",
            "endpoint": "",
        },
        {
            "code": "I-09",
            "name": "Росреестр / БТИ",
            "tz_status": "stage2",
            "stage1": "Межвед. реестр, ответы вручную",
            "endpoint": "",
        },
        {
            "code": "I-10",
            "name": "ГИБДД",
            "tz_status": "stage2",
            "stage1": "—",
            "endpoint": "",
        },
        {
            "code": "I-11",
            "name": "СФР",
            "tz_status": "stage2",
            "stage1": "—",
            "endpoint": "",
        },
        {
            "code": "I-12",
            "name": "ЗАГС / УФНС / МВД",
            "tz_status": "stage2",
            "stage1": "—",
            "endpoint": "",
        },
        {
            "code": "I-13",
            "name": "Внешний портал обращений",
            "tz_status": "done",
            "stage1": "Публичная форма + inbound API",
            "endpoint": "/public/<subsystem>/appeal/",
        },
        {
            "code": "I-14",
            "name": "SAUMI™ / внешние реестры",
            "tz_status": "stage2",
            "stage1": "—",
            "endpoint": "",
        },
    ]
