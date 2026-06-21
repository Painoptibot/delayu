# GitHub Actions — автодеплой на Jino VPS

## Почему не SSH

Jino **блокирует входящий SSH (порт 22)** с IP GitHub Actions (`Connection timed out`).
Ключ при этом может быть настроен правильно — до сервера пакет не доходит.

**Решение:** GitHub вызывает **HTTPS webhook** на вашем сайте (`delau.tech:443`), сервер сам делает `git pull` и перезапуск.

---

## 1. Однократная настройка на VPS

После `git pull` с новым кодом:

```bash
cd /opt/delayu
sudo -u delayu git pull
sudo bash deploy/setup-webhook-deploy.sh
```

Скрипт:

- установит `sudoers` для `webhook-run.sh`
- создаст `DEPLOY_WEBHOOK_TOKEN` в `.env`
- перезапустит gunicorn
- выведет значения для GitHub Secrets

Проверка с VPS:

```bash
curl -fsS -X POST "https://delau.tech/internal/deploy/" \
  -H "Authorization: Bearer ВАШ_ТОКЕН"
# {"status": "accepted"}
tail -f /opt/delayu/logs/deploy-webhook.log
```

---

## 2. GitHub Secrets

**Settings → Secrets and variables → Actions**

| Name | Значение |
|------|----------|
| `DEPLOY_URL` | `https://delau.tech` |
| `DEPLOY_WEBHOOK_TOKEN` | из `.env` на сервере |

Старые `DEPLOY_HOST`, `DEPLOY_SSH_KEY`, `DEPLOY_PASSWORD` больше не нужны.

---

## 3. Запуск

**Actions → Deploy production → Run workflow**

или любой push в `main`.

Лог деплоя на сервере: `/opt/delayu/logs/deploy-webhook.log`

---

## 4. CI (красный) — отдельно

Workflow **CI** (pytest/ruff) не влияет на сайт.

---

## 5. Ручной деплой

```bash
sudo bash /opt/delayu/deploy/update-prod.sh
```
