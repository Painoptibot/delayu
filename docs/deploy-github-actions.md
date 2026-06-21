# GitHub Actions — автодеплой на Jino VPS

## Почему не работает «облачный» runner

Jino **блокирует входящие соединения** с IP GitHub (и SSH :22, и HTTPS :443):

| Способ | Ошибка |
|--------|--------|
| SSH с Actions | `Connection timed out` |
| HTTPS webhook | `curl: (28) Connection timed out` |

С вашего ПК сайт и SSH открываются — блокируются только **диапазоны IP дата-центров GitHub**.

---

## Решение A — self-hosted runner (рекомендуется)

Runner на VPS **сам подключается к GitHub** (исходящий трафик). Inbound не нужен.

### 1. На GitHub

`Settings → Actions → Runners → **New self-hosted runner** → Linux`

Скопируйте **registration token** (действует ~1 час).

### 2. На VPS

```bash
cd /opt/delayu
sudo -u delayu git pull
sudo bash deploy/setup-github-runner.sh ВАШ_TOKEN
```

В Runners должен появиться **delayu-vps** со статусом **Online**.

### 3. Деплой

Любой push в `main` → workflow **Deploy production** выполняется **на сервере**.

Secrets (`DEPLOY_URL`, SSH и т.д.) **не нужны**.

---

## Решение B — cron (без runner)

Если runner не ставите — каждые **5 минут** cron проверяет `origin/main` и деплоит при новых коммитах:

```bash
sudo cp /opt/delayu/deploy/cron/delayu /etc/cron.d/delayu
sudo chmod 644 /etc/cron.d/delayu
```

Лог: `/opt/delayu/logs/cron-deploy.log`

После `git push` подождите до 5 минут.

---

## Webhook (локально с VPS)

`POST /internal/deploy/` работает **с самого сервера** (для ручного триггера):

```bash
sudo bash deploy/setup-webhook-deploy.sh
curl -fsS -X POST "https://delau.tech/internal/deploy/" \
  -H "Authorization: Bearer ТОКЕН_ИЗ_ENV"
```

С GitHub Actions этот URL **не достучать** — только runner или cron.

---

## Ручной деплой

```bash
sudo bash /opt/delayu/deploy/update-prod.sh
```

или

```bash
sudo bash /opt/delayu/deploy/run-deploy.sh
```

---

## CI (красный) — отдельно

Workflow **CI** (pytest/ruff) на `ubuntu-latest` — не связан с деплоем на Jino.
