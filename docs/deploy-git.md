# Git-деплой на prod (Jino VPS)

## Быстрый цикл после настройки

На сервере:

```bash
cd /opt/delayu && sudo bash deploy/update-prod.sh
```

Локально: `git push` → на сервере `update-prod.sh` (или GitHub Actions).

---

## Шаг 1 — репозиторий (локально, Windows)

```powershell
cd C:\laragon\www\newsystem
git init
git add .
git commit -m "Initial commit: Delayu platform"
git branch -M main
git remote add origin https://github.com/ВАШ_АККАUNT/newsystem.git
git push -u origin main
```

> Не коммитьте `.env` — он в `.gitignore`.

---

## Шаг 2 — первичная настройка на VPS

```bash
# HOME пользователя delayu = /opt/delayu (не /home/delayu)
sudo -u delayu mkdir -p /opt/delayu/.ssh
sudo chmod 700 /opt/delayu/.ssh
sudo -u delayu ssh-keygen -t ed25519 -f /opt/delayu/.ssh/id_ed25519 -N ""
sudo cat /opt/delayu/.ssh/id_ed25519.pub
```

Скопируйте ключ в GitHub: **Repo → Settings → Deploy keys → Add** (Read-only достаточно).

```bash
cd /opt/delayu
sudo bash deploy/setup-git-prod.sh git@github.com:ВАШ_АККАUNT/newsystem.git
```

Скрипт: `git fetch` → checkout → `update-prod.sh` → `link_superusers`.

---

## Шаг 3 — обновление после каждого push

```bash
sudo bash /opt/delayu/deploy/update-prod.sh
```

Скрипт выполняет:

1. `git pull --ff-only`
2. `deploy-app.sh` (pip, migrate, collectstatic, restart gunicorn)
3. `link_superusers` (dalayu → УЖВ)
4. `verify_platform`

---

## Шаг 4 (опционально) — автодеплой через GitHub Actions

Файл: `.github/workflows/deploy-prod.yml`

Secrets в GitHub (Settings → Secrets → Actions):

| Secret | Пример |
|--------|--------|
| `DEPLOY_HOST` | `dab7798018f1.vps.myjino.ru` |
| `DEPLOY_USER` | `root` |
| `DEPLOY_SSH_KEY` | приватный ключ root (не delayu) |
| `DEPLOY_PATH` | `/opt/delayu` |

После `git push` в `main` деплой запускается автоматически.

---

## Если `/opt/delayu` уже заполнен (FileZilla)

Вариант A — сохранить `.env` и переключиться на git:

```bash
cp /opt/delayu/.env /root/delayu.env.backup
cp /opt/delayu/.db-credentials /root/delayu.db.backup 2>/dev/null || true
mv /opt/delayu /opt/delayu.old
sudo bash deploy/setup-git-prod.sh git@github.com:USER/newsystem.git
cp /root/delayu.env.backup /opt/delayu/.env
cp /root/delayu.db.backup /opt/delayu/.db-credentials 2>/dev/null || true
sudo bash /opt/delayu/deploy/update-prod.sh
```

Вариант B — git в существующей папке (если нет `.git`):

```bash
cd /opt/delayu
sudo -u delayu git init
sudo -u delayu git remote add origin git@github.com:USER/newsystem.git
sudo -u delayu git fetch origin
sudo -u delayu git checkout -B main origin/main
sudo bash deploy/update-prod.sh
```

---

## После деплоя — проверка superuser

```bash
sudo -u delayu bash -c 'cd /opt/delayu && .venv/bin/python manage.py link_superusers'
sudo -u delayu bash -c 'cd /opt/delayu && .venv/bin/python manage.py verify_platform --username dalayu'
```

Ожидается: полное меню, главная без «Выберите подсистему», ссылки без 500.
