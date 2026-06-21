# Acceptance: 50 улучшений «ДелаЮ» (newsystem)

**Подсистема:** `pilot` · **Логин:** `demo`/`demo`, `admin`/`admin`  
**DoD:** D1 API · D2 UI · D3 права · D4 аудит · D5 seed · D6 не stub


| #   | Given / When / Then                                                         | UI / API                                |
| --- | --------------------------------------------------------------------------- | --------------------------------------- |
| 1   | Given seed_demo · When открыть паспорт · Then PDF/разделы модулей           | `/exploit/product-passport/`            |
| 2   | Given membership pilot · When переключить подсистему · Then меню обновилось | `/switch-subsystem/`                    |
| 3   | Given роль specialist · When открыть реестр без M22 · Then 403              | RBAC middleware                         |
| 4   | Given паспорт · When экспорт compliance CSV · Then файл скачан              | кнопка на паспорте                      |
| 5   | Given compliance snapshot · When просмотр · Then строки модулей             | `/exploit/product-passport/`            |
| 6   | Given DELAYU_DEMO_MODE · When POST bulk · Then 403 + баннер                 | `/cases/bulk/`                          |
| 7   | Given AiPolicy · When invoke assistant · Then лимит в журнале               | `/ai/`                                  |
| 8   | Given registry · When список экранов · Then URL и модули                    | `/exploit/registry/`                    |
| 9   | Given retention policy · When сохранить · Then audit + archive years        | `/exploit/pii/`                         |
| 10  | Given org A/B · When API cases user A · Then только дела org A              | `GET /api/v1/cases/`                    |
| 11  | Given privacy toggle · When включить · Then session privacy_mode + blur     | navbar + `POST /platform/privacy-mode/` |
| 12  | Given audit · When create case · Then запись AuditLog                       | `/administration/audit/`                |
| 13  | Given delegation · When создать · Then задачи principal видны               | `/workspace/cabinet/access/`            |
| 14  | Given 2FA admin · When verify TOTP · Then session 2fa_verified              | `/auth/2fa/verify/`                     |
| 15  | Given bulk · When первый POST · Then reauth redirect                        | `/auth/reauth/`                         |
| 16  | Given audit · When export snapshot · Then CSV/JSON                          | `/administration/audit/snapshot/`       |
| 17  | Given case 360 · When вкладки · Then timeline + stats                       | `/cases/<pk>/`                          |
| 18  | Given SSO provider · When start OIDC · Then redirect metadata               | `/auth/sso/<pk>/start/`                 |
| 19  | Given SSO callback · When code exchange · Then login session                | `/auth/sso/callback/`                   |
| 20  | Given sessions · When revoke · Then logout другой сессии                    | `/workspace/cabinet/security/`          |
| 21  | Given NSI case_kind · When список типов · Then 4+ значения                  | `/ops/case-kinds/`                      |
| 22  | Given FormSchema · When создать дело · Then extra_data сохранён             | `/cases/new/`, `/ops/forms/`            |
| 23  | Given NSI · When CRUD classifier · Then choices в формах                    | `/ops/nsi/`                             |
| 24  | Given BPM template · When studio editor · Then steps JSON                   | `/studio/bpm/`                          |
| 25  | Given SLA rule · When monitor · Then просрочки                              | `/bpm/sla/monitor/`                     |
| 26  | Given tasks · When today view · Then KPI + таблица                          | `/workspace/today/`                     |
| 27  | Given document · When версия + hash · Then vN + sha256 в 360°               | вкладка «Документы» дела                |
| 28  | Given print template · When render · Then подстановка переменных            | `/correspondence/print/`                |
| 29  | Given saved filter · When favorites · Then фильтр применим                  | `/workspace/favorites/`                 |
| 30  | Given case · When tab links · Then граф связей                              | `/cases/<pk>/?tab=links`                |
| 31  | Given ReportSchedule · When run command · Then отчёт создан                 | `/analytics/reports/`                   |
| 32  | Given ETL run · When error_rows · Then modal протокол                       | `/infra/etl/`                           |
| 33  | Given cases bulk · When reauth+POST · Then статус изменён                   | `/cases/`                               |
| 34  | Given integration queue · When retry API · Then status pending              | `/integrations/messages/`               |
| 35  | Given inbound · When register + AI · Then corr + audit classify             | `/correspondence/inbound/new/`          |
| 36  | Given MailDeliveryLog · When API · Then metrics                             | `/exploit/mail/delivery/`               |
| 37  | Given SignatureRequest · When mock sign · Then signed                       | `/correspondence/signatures/`           |
| 38  | Given openapi.json · When paths · Then ai/policy + integration              | `/api/v1/openapi.json`                  |
| 39  | Given pgvector · When hybrid search · Then score > 0                        | `/platform/search/`                     |
| 40  | Given classify · When preview · Then reasons + confidence                   | inbound preview / `/ai/tools/`          |
| 41  | Given AiPolicy · When PATCH API · Then max_requests updated                 | `PATCH /api/v1/ai/policy/`              |
| 42  | Given HITL · When approve/reject · Then status changed                      | `/ai/hitl/`                             |
| 43  | Given API key · When rate exceeded · Then 429                               | `/api/v1/cases/`                        |
| 44  | Given semantic search · When query · Then hits from index                   | `/ai/tools/` search                     |
| 45  | Given AiFeedback · When POST · Then запись + audit                          | `/ai/feedback/`                         |
| 46  | Given today widgets · When save form · Then theme_prefs                     | `/workspace/today/widgets/`             |
| 47  | Given case 360 · When all tabs · Then overview..ai                          | `/cases/<pk>/`                          |
| 48  | Given layout · When Tab · Then skip-link focus                              | `#main-content`                         |
| 49  | Given viewport 375px · When cases list · Then card rows                     | mobile CSS                              |
| 50  | Given onboarding · When mark step · Then progress %                         | `/platform/onboarding/`                 |


