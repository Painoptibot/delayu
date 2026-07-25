# Odysseus local runbook (Delayu M87)

## Purpose

Odysseus runs as a **separate** self-hosted AI workspace. Delayu integrates via reverse proxy (`/ai/odysseus/`) and settings (module **M87**). Do not copy Odysseus source into `delayu/` (AGPL).

## Prerequisites

- Docker Desktop / Engine
- Git
- Delayu running (`http://127.0.0.1:8000/`)

## First-time vendor pin

```bash
mkdir -p vendor
git clone https://github.com/odysseus-dev/odysseus.git vendor/odysseus
cd vendor/odysseus
git checkout <TAG_OR_SHA>   # pin — record in Odysseus settings UI
cp .env.example .env
```

From Delayu repo root:

```bash
docker compose -f vendor/odysseus/docker-compose.yml -f deploy/odysseus/compose.delayu.yml up -d --build
```

Open Odysseus directly: `http://127.0.0.1:7000`  
First admin password: `docker compose ... logs odysseus` (see upstream README).

## Delayu UI

1. Enable module **M87** for the subsystem (catalog / studio).
2. Open **ИИ → Odysseus** (`/ai/odysseus/`).
3. **Настройки**: set `base_url=http://127.0.0.1:7000`, enable, save pin ref, **Проверить health**.

## Managed updates (P2)

```bash
python manage.py odysseus_update --check
python manage.py odysseus_update --apply <REF>
python manage.py odysseus_update --rollback
```

Apply/rollback also available to platform admins in settings UI when P2 is shipped. Never auto-pull without confirmation.

## Security

- Keep compose ports on `127.0.0.1` only (see `deploy/odysseus/compose.delayu.yml`).
- Do not expose Odysseus publicly; it has powerful local tools.
