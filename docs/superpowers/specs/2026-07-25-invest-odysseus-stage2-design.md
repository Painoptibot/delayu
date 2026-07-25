# Design: Stage 2 вЂ” Odysseus module (proxy B) + Invest 30 improvements

**Date:** 2026-07-25  
**Status:** draft for review  
**Branch (planned):** `feature/invest-odysseus-stage2`  
**Control model:** Approach **B** вЂ” single stage/branch, stacked packages with mandatory pytest gate between packages

## Goal

1. Add platform module **Odysseus workspace** to Delayu: local Docker runtime, settings UI, reverse-proxy embed (mode B), **managed** upstream updates (pin / check / apply / rollback).
2. Hook Odysseus into the **invest** subsystem with project/site context.
3. Deliver all **30 invest improvements** in the same stage via stacked packages P4вЂ“P9.

## Decisions (approved)

| Topic | Choice |
| --- | --- |
| Odysseus role | Platform module, then invest hook |
| Integration | **B** вЂ” local deploy + reverse proxy into Delayu |
| Updates | From upstream repo, **controlled** (no unattended auto-pull) |
| Stage shape | **Everything in one stage**, with control |
| Control mechanism | **B** вЂ” stacked commit packages + pytest gate (not feature-flag dark launch) |
| License posture | Keep Odysseus as separate vendor tree (AGPL); do **not** copy core into `delayu/` |

## Out of scope

- Copying/forking Odysseus application code into `delayu/` Python package
- Unattended cron auto-update of vendor
- Public exposure of Odysseus ports (loopback / private network only)
- Replacing existing M47 AI hub (Odysseus is additive M87)

---

## Architecture overview

```
Delayu (Django)
  M87 OdysseusSettings + admin UI
  /ai/odysseus/          в†’ shell (health, open workspace)
  /ai/odysseus/proxy/**  в†’ reverse proxy в†’ Odysseus :7000
  invest cards           в†’ context bridge в†’ shell/proxy

vendor/odysseus/         (git pin: tag or SHA)
deploy/odysseus/         (compose overlay, loopback)
manage.py odysseus_update --check|--apply|--rollback
```

Stacked packages on one branch:

| Package | Content | Gate |
| --- | --- | --- |
| P0 | M87 + settings model + compose overlay + health | unit + health |
| P1 | Proxy + auth bridge + shell UI | integration |
| P2 | Managed update command + UI actions + audit | cmd tests |
| P3 | Invest hook (project/site/dashboard) | invest UI tests |
| P4вЂ“P9 | 30 improvements in blocks of ~5 | block pytest |
| P10 | Final smoke (invest + odysseus + automation UI) | targeted full suite |

**Rule:** package N is not accepted until its pytest gate is green.

---

## Odysseus module (P0вЂ“P2) вЂ” approved

### Catalog / menu

- Module code: **`M87`** В«Odysseus workspaceВ» (M49 already used by classification in catalog)
- AI section nav pill: В«OdysseusВ» (alongside M47/M48)

### Model `OdysseusSettings`

Per-subsystem (or global with optional subsystem override вЂ” implement as OneToOne to `Subsystem` for invest-first, allow platform-wide default later):

| Field | Purpose |
| --- | --- |
| `enabled` | Master switch |
| `base_url` | Default `http://127.0.0.1:7000` |
| `embed_mode` | `iframe` \| `new_tab` \| `proxy_shell` |
| `pinned_ref` | Git tag or SHA |
| `upstream_url` | Default official repo URL |
| `vendor_path` | Default `vendor/odysseus` |
| `auth_mode` | `none_dev` \| `shared_secret` \| `header_bridge` |
| `shared_secret` | Optional |
| `allowed_path_prefixes` | JSON list |
| `timeout_s` | Proxy timeout |
| `role_allowlist` | JSON list of role codes for invest hook (default admin/dept) |
| `last_health_at` / `last_health_ok` | Health cache |
| `options` | JSON extras (provider hints for UI) |
| `previous_pinned_ref` | For rollback |

### Local runtime

- Vendor checkout at pinned ref under `vendor/odysseus` (git submodule **or** managed clone вЂ” prefer managed clone via command for simpler Windows/Laragon).
- Compose: upstream compose + `deploy/odysseus/compose.delayu.yml` (loopback bind).
- Docs: `docs/odysseus-local.md` (start, logs, admin password, Ollama notes).

### Proxy (mode B)

- Shell: `/ai/odysseus/` вЂ” Delayu chrome, health, CTA.
- Proxy: `/ai/odysseus/proxy/<path>` вЂ” streaming reverse proxy (httpx/ASGI):
  - Require auth + membership + `enabled` + M87 view
  - Allowlist path prefixes
  - Strip hop-by-hop headers
  - Optional `header_bridge`: `X-Delayu-User`, `X-Delayu-Subsystem`
  - Upstream down в†’ shell shows fail state, no uncaught 500

### Managed updates

```
manage.py odysseus_update --check
manage.py odysseus_update --apply REF
manage.py odysseus_update --rollback
```

- `--check`: fetch tags/commits, compare to `pinned_ref`, show summary (no mutate)
- `--apply REF`: backup current pin в†’ `previous_pinned_ref`, checkout REF, update settings, audit; on failure leave pin unchanged
- `--rollback`: restore `previous_pinned_ref`
- UI: platform admin / superuser only for apply/rollback; audit every action
- **No** unattended auto-pull

---

## Invest hook (P3) вЂ” approved

- CTA В«РћС‚РєСЂС‹С‚СЊ РІ OdysseusВ» on project detail, site detail, invest hub/dashboard when settings enabled + role in allowlist + M87.
- Context payload: subsystem code, project/site ids, compact snapshot (code, stage, org, overdue flags, automation readiness) + prompt template.
- Open via `embed_mode` (iframe in shell or new tab to proxy).
- Audit: user, object type/id, pin ref, timestamp.

---

## Thirty improvements вЂ” package map (P4вЂ“P9) вЂ” approved

| Package | Items |
| --- | --- |
| **P4 Ops** | 1 Today inbox, 2 SLAв†’notifications, 3 return templates, 4 package attachments, 5 bulk stage update |
| **P5 Quality** | 6 legal entity card, 7 dedupe UI, 8 package versions UI, 27 card audit trail, 30 completeness coach |
| **P6 Sites** | 9 map, 10 booking calendar / expiry, 11 candidate compare, 12 EGRN history, 13 restriction zones |
| **P7 Integrations** | 14 Bitrix live, 15 webhook security UI, 16 SMEV live, 17 stage sync conflicts, 18 push+gate on card, 19 sandbox simulator вЂ” split **P7a** (14вЂ“16) / **P7b** (17вЂ“19) |
| **P8 Dashboard** | 20 meeting export, 21 industry/investment metrics, 22 kanban, 23 period compare, 28 escalation rules UI |
| **P9 UX/auto** | 24 role homes, 25 hide 403 menu items, 26 new-project wizard, 29 auto-assign owner |

Each package ends with focused pytest + invest/automation smoke as needed.

---

## Access, errors, tests, risks вЂ” approved

### Access

- Settings + update apply/rollback: `is_platform_admin` / superuser
- Proxy/shell: authenticated + M87 + enabled
- Invest CTA: role allowlist (default `invest_admin`, `invest_dept` + platform)

### Errors

- Upstream down в†’ degraded shell
- Path not allowlisted в†’ 404
- Failed apply в†’ pin unchanged
- Oversized invest context в†’ truncate + warning

### Tests

- P0вЂ“P2: settings, health mock, proxy allow/deny, update dry-run paths
- P3: CTA visibility + context shape
- P4вЂ“P9: domain tests per package
- P10: `test_invest_automation_ui` + odysseus + new package suites
- Gate: no green tests в†’ package not closed

### Risks

- Stage volume is very large; only stacked gates keep it controllable
- AGPL: vendor isolation mandatory
- Odysseus tools/shell: loopback-only
- Live Bitrix/SMEV may ship as adapters + sandbox fallback if external systems unavailable

---

## Success criteria

1. Local Odysseus runs and is reachable via Delayu proxy shell with health status.
2. Updates are pin-based with check/apply/rollback and audit.
3. Invest users with allowlisted roles can open Odysseus with project/site context.
4. All 30 improvements land in stacked packages with pytest gates.
5. Final smoke green for invest + odysseus + existing automation UI tests.

## Non-goals reminder

Odysseus does not replace M47; it is an optional powerful workspace behind M87.

