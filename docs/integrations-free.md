# Бесплатные интеграции «ДелаЮ» / АИС УЖВ

**СМЭВ, ГИС ЖКХ (официальный), Катарсис** — вне этого списка (этап 2, I-xx).

Полная сводка (50 улучшений vs I-01…I-14 vs этот список): [integrations-status.md](./integrations-status.md).

## Статус

| # | Интеграция | Настройка | Cron / URL |
|---|------------|-----------|------------|
| 1 | DaData (адрес, ФИО, телефон…) | `DADATA_API_KEY` в `.env` | формы УЖВ |
| 2 | Яндекс.Карты | `YANDEX_MAPS_API_KEY` | `/uzhv/fund/map/` |
| 3 | Исходящие webhook | коннектор `webhook_uzhv`, n8n | `process_integration_queue` |
| 4 | Входящие API (ЕПГУ) | `epgu_uzhv`, secret | `POST /api/v1/integration/inbound/uzhv/epgu_uzhv/` |
| 4b | МФЦ (I-07) | `mfc_uzhv` | `POST .../inbound/uzhv/mfc_uzhv/` |
| 5 | Публичная форма | — | `/public/uzhv/appeal/` |
| 6 | 1С JSON (входящий) | `external_1c_uzhv` | `POST .../inbound/uzhv/external_1c_uzhv/` |
| 7 | Telegram | `TELEGRAM_BOT_TOKEN`, M41 | `POST /api/v1/telegram/uzhv/` |
| 8 | MAX | канал `max_uzhv` | журнал M78 |
| 9 | E-mail SMTP | `EMAIL_*` в `.env` | шаблоны M78 |
| 10 | Web Push | `UZHV_VAPID_*` | кабинет / hub |
| 11 | iCal сроки | — | `/uzhv/deadlines/export/?format=ical` |
| 12 | SSO / OIDC / ЕСИА демо | `/infra/sso/` | вход |
| 13 | REST + OpenAPI | API-ключ M43 | `/api/v1/openapi.json` |
| 14 | QR на карточки | кнопка **QR** в модалке; обзор УЖВ | `/uzhv/qr/citizens/<id>.svg`, appeals, cases, public |
| 15 | IMAP входящая почта | Эксплуатация → Почта | `sync_inbound_mail` |
| 16 | Портал гражданина (M72) | `/infra/citizen/` | внутренний |

## Одна команда cron

```bash
python manage.py setup_free_integrations
python manage.py integrations_cron --all-uzhv
```

Импорт выгрузки ГИС ЖКХ (CSV, PY-01): `data/gis_zhkh_fund.example.csv`

## Опционально

```env
UZHV_PUBLIC_APPEAL_TOKEN=   # если пусто — публичная форма без токена (только dev)
TELEGRAM_WEBHOOK_SECRET=
```

После изменений seed:

```bash
python manage.py seed_uzhv
python manage.py sync_uzhv_role_permissions
```
