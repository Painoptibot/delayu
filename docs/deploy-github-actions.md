# GitHub Actions — автодеплой на Jino VPS

## 1. SSH-ключ для Actions (рекомендуется)

Jino часто **не пускает root по паролю** с IP GitHub. Надёжнее ключ.

На **VPS** (от root):

```bash
ssh-keygen -t ed25519 -f /root/.ssh/github_actions_deploy -N ""
cat /root/.ssh/github_actions_deploy.pub >> /root/.ssh/authorized_keys
chmod 700 /root/.ssh
chmod 600 /root/.ssh/authorized_keys /root/.ssh/github_actions_deploy
cat /root/.ssh/github_actions_deploy
```

Скопируйте **весь** вывод (от `-----BEGIN` до `-----END`).

GitHub → **Settings → Secrets → New secret**:

| Name | Значение |
|------|----------|
| `DEPLOY_SSH_KEY` | приватный ключ целиком |

`DEPLOY_PASSWORD` можно удалить.

---

## 2. Обязательные Secrets

| Name | Значение |
|------|----------|
| `DEPLOY_HOST` | `dab7798018f1.vps.myjino.ru` |
| `DEPLOY_USER` | `root` |

---

## 3. Запуск

**Actions → Deploy production → Run workflow**

Или любой push в `main`.

---

## 4. CI (красный «CI #2») — отдельно от деплоя

Workflow **CI** гоняет тесты на GitHub — падение CI **не мешает** сайту, если деплой зелёный.

Пока можно игнорировать или починить позже (`pytest` / `ruff`).

---

## 5. Ручной деплой (если Actions не нужен)

```bash
sudo bash /opt/delayu/deploy/update-prod.sh
```

Или после push с Windows:

```bash
cd /opt/delayu && sudo -u delayu git pull && sudo bash deploy/deploy-app.sh
```
