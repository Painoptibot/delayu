# Статус интеграций — сводка

**Обновлено:** 27.05.2026

## Три разных списка (не путать)

| Список | Что это | Статус |
|--------|---------|--------|
| **50 улучшений** | UX/платформа «ДелаЮ» ([improvements-50-status.md](./improvements-50-status.md)) | MVP+ по всем пунктам |
| **I-01…I-14** | Официальные внешние ИС из ТЗ УЖВ | **Не в этапе 1** — см. матрицу ниже |
| **16 бесплатных** | Замены без СМЭВ ([integrations-free.md](./integrations-free.md)) | См. таблицу «Бесплатный контур» |

---

## Бесплатный контур (этап 1) — что готово / что настроить

| # | Интеграция | Код | Готово в коде | Нужно от вас |
|---|------------|-----|---------------|--------------|
| 1 | DaData | `dadata` | ✅ API + формы УЖВ | `DADATA_API_KEY` в `.env` |
| 2 | Яндекс.Карты | `yandex_maps` | ✅ карта фонда | `YANDEX_MAPS_API_KEY` |
| 3 | Webhook / n8n | `webhook_uzhv`, `n8n_uzhv` | ✅ очередь + HTTP POST | Включить коннектор, URL webhook |
| 4 | ЕПГУ inbound | `epgu_uzhv` | ✅ handler | `seed_uzhv`, secret в заголовке |
| 5 | МФЦ inbound | `mfc_uzhv` | ✅ handler (I-07) | `seed_uzhv`, secret `uzhv-mfc-demo-secret` |
| 6 | 1С JSON | `external_1c_uzhv` | ✅ handler + тесты | secret `uzhv-1c-demo-secret` |
| 7 | Публичная форма | `public_form` | ✅ `/public/uzhv/appeal/` | опц. `UZHV_PUBLIC_APPEAL_TOKEN` |
| 8 | Telegram | `telegram` | ✅ inbound + send | `TELEGRAM_BOT_TOKEN`, webhook |
| 9 | MAX | `max` | ✅ журнал + HTTP если URL | URL API в канале `max_uzhv` |
| 10 | SMTP | `email` | ✅ M78 | `EMAIL_*` (не console) |
| 11 | Web Push | `webpush` | ✅ | `UZHV_VAPID_*` |
| 12 | iCal | `ical` | ✅ | — |
| 13 | SSO демо | `sso` | ✅ после seed | `seed_uzhv` |
| 14 | REST/OpenAPI | — | ✅ M43 | API-ключ |
| 15 | QR карточки | — | ✅ модалки + обзор | — |
| 16 | IMAP | — | ✅ `sync_inbound_mail` | IMAP в «Эксплуатация → Почта» |
| — | События УЖВ | — | ✅ смена статусов → webhook | `process_integration_queue` / cron |
| — | PY-01…PY-07 | — | ✅ CLI | cron по [rukovodstvo](./uzv/rukovodstvo-polzovatelya.md) |

**Не в этапе 1:** СМЭВ, ГИС ЖКХ, Катарсис (I-01, I-08) — страница `/integrations/smev/` только демо.

---

## I-01…I-14 (ТЗ) — замены на этапе 1

| Код | Система | Этап 1 | Статус |
|-----|---------|--------|--------|
| I-01 | ГИС ЖКХ | PY-01 импорт | этап 2 |
| I-02 | АИС «Жилье» | вручную | этап 2 |
| I-03 | ФРТ | поля расселения | этап 2 |
| I-04 | Минтруд | /uzhv/orphans/ | вручную |
| I-05 | ЕПГУ | API + форма | **частично** |
| I-06 | Уведомления ЕПГУ | M78 + PY-07 | **частично** |
| I-07 | МФЦ | `mfc_uzhv` API | **частично** |
| I-08 | Катарсис/СМЭВ | — | этап 2 |
| I-09…I-12 | Росреестр…МВД | межвед. вручную | этап 2 |
| I-13 | Внешний портал | публичная форма | **готово** |
| I-14 | SAUMI | — | этап 2 |

Матрица в UI: **Шлюз интеграций** (подсистема УЖВ).

---

## Команды

```bash
python manage.py setup_free_integrations
python manage.py uzhv_py01_import data/gis_zhkh_fund.example.csv --subsystem uzhv --kind fund
```

Отдельно:

```bash
python manage.py seed_uzhv
python manage.py integrations_cron --all-uzhv
python manage.py process_integration_queue
```

(`--all-uzhv` по умолчанию включает PY-07; отключить: `--no-py07`)

## Тесты

```bash
pytest delayu/tests/test_integration_inbound.py delayu/tests/test_integration_events.py delayu/tests/test_integration_1c.py -q
```
