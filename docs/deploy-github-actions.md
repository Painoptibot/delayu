# GitHub Actions — автодеплой на Jino VPS

## 1. SSH-ключ для Actions (обязательно)

Jino **не пускает root по паролю** с IP GitHub. Нужен ключ **для входа root**, не ключ git (`/opt/delayu/.ssh/id_ed25519`).

На **VPS** (от root):

```bash
sudo bash /opt/delayu/deploy/setup-github-actions-ssh.sh
```

Скрипт выведет fingerprint и `LOCAL_OK`, если sshd принимает ключ.

GitHub → **Settings → Secrets**:

| Name | Значение |
|------|----------|
| `DEPLOY_SSH_KEY` | приватный ключ целиком (`-----BEGIN OPENSSH PRIVATE KEY-----` …) |

Если многострочная вставка ломается — используйте **одну строку base64** из вывода скрипта:

| Name | Значение |
|------|----------|
| `DEPLOY_SSH_KEY_B64` | строка base64 без переносов |

`DEPLOY_PASSWORD` можно удалить.

### Ошибка `attempted methods [none password publickey]`

Ключ до GitHub доходит, но **не совпадает** с `authorized_keys` на сервере.

1. Заново: `sudo bash /opt/delayu/deploy/setup-github-actions-ssh.sh`
2. Обновите secret (не путать с git-ключом delayu)
3. В логе Actions смотрите **Key fingerprint** — должен совпадать с fingerprint на VPS
4. `DEPLOY_USER` = `root`, `DEPLOY_HOST` = `dab7798018f1.vps.myjino.ru` (без `https://`)

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
