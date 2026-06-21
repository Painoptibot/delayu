# Статус 50 улучшений — платформа «ДелаЮ» (newsystem)

**Обновлено:** 27.05.2026  
**Подсистема для проверки:** `pilot`  
**DoD:** D1 API · D2 UI · D3 права · D4 аудит · D5 seed · D6 не stub  
**Приёмка:** [acceptance-50.md](./acceptance-50.md) · **Задачи:** [improvements-50-tasks.md](./improvements-50-tasks.md)

| # | Тема | Статус | Примечание |
|---|------|--------|------------|
| 1 | Паспорт продукта | **MVP+** | `/exploit/product-passport/` |
| 2 | Tenant / membership | **Работает** | middleware + switch |
| 3 | RBAC по модулям | **Работает** | PermissionGrant |
| 4 | Каталог модулей реестра | **MVP+** | seed_registry_platform |
| 5 | Compliance snapshot | **MVP+** | DEFAULT_COMPLIANCE |
| 6 | Демо-режим | **MVP+** | DELAYU_DEMO_MODE, middleware, баннер |
| 7 | AI Gateway | **MVP+** | лимиты, invoke |
| 8 | Реестр экранов/API | **MVP+** | registry_platform |
| 9 | Политика ПДн / retention | **MVP+** | PiiMaskingPolicy + DataRetentionPolicy |
| 10 | Org scope | **MVP+** | `org_scope.py`, API + реестр |
| 11 | Privacy mode | **MVP+** | session + GET/POST `/platform/privacy-mode/` |
| 12 | Audit append-only | **Работает** | тесты |
| 13 | Делегирование | **MVP+** | delegation service |
| 14 | 2FA TOTP | **MVP+** | setup/verify |
| 15 | Re-auth критичных ops | **MVP+** | `/auth/reauth/` |
| 16 | Audit snapshots | **MVP+** | export + UI |
| 17 | Case 360° | **MVP+** | tabs timeline |
| 18 | SSO | **MVP+** | OIDC + demo metadata |
| 19 | SSO production | **MVP+** | token exchange |
| 20 | Session registry | **MVP+** | revoke list |
| 21 | Типы дел M03 | **MVP+** | NSI `case_kind`, `/ops/case-kinds/` |
| 22 | M04 конструктор | **MVP+** | FormSchema, `/ops/forms/` |
| 23 | M05 НСИ | **MVP+** | `/ops/nsi/` |
| 24 | M06 workflow | **MVP+** | BPM + `/studio/bpm/` |
| 25 | M07 SLA | **MVP+** | `/bpm/sla/` |
| 26 | M08 задачи | **MVP+** | workplace today/kanban |
| 27 | M09 ECM | **MVP+** | версии, SHA-256 в 360° |
| 28 | M10 печать | **MVP+** | PrintTemplate |
| 29 | M14 поиск | **MVP+** | SavedFilter + global search |
| 30 | Связи сущностей | **MVP+** | `build_case_link_graph`, tab links |
| 31 | Report schedule | **MVP+** | ReportSchedule + command |
| 32 | Import / ETL errors | **MVP+** | error_rows + modal |
| 33 | Bulk на `/cases/` | **MVP+** | bulk + reauth |
| 34 | Exchange queue | **MVP+** | dead letter + API |
| 35 | Inbound correspondence | **MVP+** | wizard + AI + create case |
| 36 | SMTP delivery | **MVP+** | MailDeliveryLog + API |
| 37 | КЭП | **MVP+** | SignatureRequest + mock |
| 38 | OpenAPI | **MVP+** | integration, notifications, ai/policy |
| 39 | pgvector | **Работает** | hybrid search |
| 40 | Explainability classify | **MVP+** | reasons + confidence |
| 41 | AiPolicy edit | **MVP+** | UI + PATCH API |
| 42 | HITL | **MVP+** | AiHumanReview |
| 43 | API rate limits | **MVP+** | gateway 429 |
| 44 | Semantic search | **MVP+** | embeddings + index |
| 45 | AiFeedback | **MVP+** | модель + UI |
| 46 | Workplace widgets | **MVP+** | today_widgets |
| 47 | Карточка 360° | **MVP+** | все вкладки |
| 48 | a11y | **MVP+** | delayu-a11y.css |
| 49 | Mobile 375px | **MVP+** | delayu-mobile.css |
| 50 | Onboarding | **MVP+** | `/platform/onboarding/` |

## Волна S6

- `#11` — privacy: session `privacy_mode`, GET/POST API, sync JS
- `#21` — NSI `case_kind`, `/ops/case-kinds/`
- `#30` — граф связей в tab «Связи»
- `#27` — SHA-256 в списке документов 360°
- `#10` — org scope (продолжение)
- F0 — `acceptance-50.md`, `improvements-50-tasks.md`

## F7 — acceptance smoke

- `delayu/tests/test_acceptance_50.py` — UI-маршруты, API, privacy, OpenAPI, CSS a11y/mobile

## Команды проверки

```cmd
manage.bat seed_demo
manage.bat test delayu.tests.test_registry_wave_s6
manage.bat test delayu.tests.test_acceptance_50
manage.bat test
```
