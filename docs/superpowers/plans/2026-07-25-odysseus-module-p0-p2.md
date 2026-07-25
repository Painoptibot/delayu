# Odysseus Module + Stage2 Stack — Implementation Plan (P0–P2 first)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Ship Delayu module for local Odysseus (settings, health, reverse proxy, managed updates), then continue stacked packages P3–P10 per stage2 design.

**Architecture:** Vendor Odysseus at pinned git ref under `vendor/odysseus` (not copied into `delayu/`). Delayu owns `OdysseusSettings`, shell UI, reverse proxy `/ai/odysseus/proxy/`, and `odysseus_update` management command. Module code **M87** (M49 already used by classification).

**Tech Stack:** Django, httpx/ASGI proxy, Docker Compose, pytest-django.

**Spec:** `docs/superpowers/specs/2026-07-25-invest-odysseus-stage2-design.md`

## Global Constraints

- Approach B: stacked packages; pytest gate before closing each package.
- AGPL: do not copy Odysseus app code into `delayu/`.
- Loopback-only Odysseus bind by default.
- No unattended auto-update.
- Module code: **M87** (deviation from draft spec M49 — catalog collision).
- Commits per package gate; English conventional messages.
- Branch: `feature/invest-odysseus-stage2`.

## Spec deviation

| Draft | Actual |
| --- | --- |
| M49 | **M87** «Odysseus workspace» |

Update design doc when P0 lands.

## File map (P0–P2)

| File | Responsibility |
| --- | --- |
| `delayu/models_odysseus.py` | `OdysseusSettings` |
| `delayu/migrations/0077_odysseus_settings.py` | Schema + ModuleCatalog M87 seed via RunPython if needed |
| `delayu/data/modules_full.py` | Add M87 |
| `delayu/services/odysseus_settings.py` | ensure/get settings, health check |
| `delayu/services/odysseus_proxy.py` | allowlist + proxy helpers |
| `delayu/services/odysseus_update.py` | check/apply/rollback |
| `delayu/views_odysseus.py` | shell, settings POST, proxy view |
| `delayu/forms_odysseus.py` | settings form |
| `delayu/management/commands/odysseus_update.py` | CLI |
| `delayu/urls.py` | routes |
| `delayu/menu.py` + `templates/platform/ai/_nav.html` | nav |
| `templates/platform/ai/odysseus_shell.html` | UI |
| `templates/platform/ai/odysseus_settings.html` | settings |
| `deploy/odysseus/compose.delayu.yml` | overlay |
| `docs/odysseus-local.md` | runbook |
| `delayu/tests/test_odysseus_module.py` | tests |
| `.gitignore` | allow `vendor/odysseus` policy note |

---

### Task 1: M87 catalog + OdysseusSettings model (P0 start)

**Files:**
- Create: `delayu/models_odysseus.py`
- Modify: `delayu/models.py` (import)
- Modify: `delayu/data/modules_full.py`
- Create: migration via makemigrations
- Test: `delayu/tests/test_odysseus_module.py`

**Interfaces:**
- Produces: `OdysseusSettings` OneToOne `Subsystem`; `ensure_odysseus_settings(subsystem)`

- [ ] **Step 1: Failing test**

```python
# delayu/tests/test_odysseus_module.py
import pytest
from delayu.models import ModuleCatalog, Subsystem
from delayu.models_odysseus import OdysseusSettings
from delayu.services.odysseus_settings import ensure_odysseus_settings

@pytest.mark.django_db
def test_m87_in_catalog_data():
    from delayu.data.modules_full import MODULES
    codes = [m[0] for m in MODULES]
    assert "M87" in codes

@pytest.mark.django_db
def test_ensure_odysseus_settings_defaults():
    sub = Subsystem.objects.create(code="ody-t", name="Ody", industry_template="invest", status="active")
    cfg = ensure_odysseus_settings(sub)
    assert cfg.base_url.startswith("http://127.0.0.1:7000")
    assert cfg.enabled is False
    assert cfg.pinned_ref == ""
    assert OdysseusSettings.objects.filter(subsystem=sub).count() == 1
```

- [ ] **Step 2: Run RED** — `pytest delayu/tests/test_odysseus_module.py -v`

- [ ] **Step 3: Implement model + ensure + modules_full M87 + migration**

```python
# delayu/models_odysseus.py (fields per design: enabled, base_url, embed_mode, pinned_ref, ...)
```

- [ ] **Step 4: GREEN + commit** `feat(odysseus): add M87 settings model`

---

### Task 2: Health check service (P0)

**Files:** `delayu/services/odysseus_settings.py`, tests

- [ ] **Step 1:** Test `check_odysseus_health` with httpx mock / responses: ok updates `last_health_ok=True`; connection error → False
- [ ] **Step 2:** Implement using httpx GET `{base_url}/` timeout
- [ ] **Step 3:** Commit `feat(odysseus): add health check`

---

### Task 3: Settings UI + shell stub (P0)

**Files:** forms, views, templates, urls, menu, ai `_nav.html`

- [ ] Settings GET/POST for platform admin; shell page shows health + enabled state
- [ ] Tests: admin can GET shell 200; agency without M87 redirected/forbidden per ModulePermissionMixin
- [ ] Commit `feat(odysseus): add settings and shell UI`

---

### Task 4: Compose overlay + docs (P0 gate)

**Files:** `deploy/odysseus/compose.delayu.yml`, `docs/odysseus-local.md`, `.gitignore` entry for vendor optional

- [ ] Document clone/pin/docker up; do **not** require vendor in repo for tests
- [ ] Commit `docs(odysseus): local runbook and compose overlay`
- [ ] **P0 GATE:** `pytest delayu/tests/test_odysseus_module.py -v` all green

---

### Task 5: Reverse proxy (P1)

**Files:** `odysseus_proxy.py`, proxy view, tests allow/deny

- [ ] Allowlisted path proxied; non-allowlist 404; disabled settings 403/redirect
- [ ] Commit `feat(odysseus): add reverse proxy`
- [ ] **P1 GATE:** proxy tests green

---

### Task 6: Managed updates (P2)

**Files:** `odysseus_update.py` service + management command + UI actions + audit

- [ ] `--check` / `--apply` / `--rollback` with temp dir fixtures (no real github required — mock git)
- [ ] Commit `feat(odysseus): managed update check/apply/rollback`
- [ ] **P2 GATE:** update tests green

---

### Later packages (outline only — separate task briefs when starting)

- **P3** Invest CTA + context bridge
- **P4–P9** Thirty improvements per design table
- **P10** Final smoke

Update design doc module code M49→M87 in same PR as Task 1.

## Execution note

Start Task 1 immediately on `feature/invest-odysseus-stage2`. Prefer SDD or inline execution; do not start P3 until P0–P2 gates pass.
