# Деплой на Ubuntu 24.04 LTS

Пошаговая инструкция для VPS с **ДелаЮ / АИС УЖВ**.

## Что получится

| Компонент | Как |
|-----------|-----|
| Приложение | Gunicorn → `127.0.0.1:8000`, systemd `delayu` |
| БД | PostgreSQL 16 + pgvector |
| Веб | Nginx (static/media + reverse proxy) |
| HTTPS | Certbot (Let's Encrypt) |
| Cron | PY-05, integrations, отчёты, бэкап |

Каталог на сервере по умолчанию: **`/opt/delayu`**, пользователь **`delayu`**.

---

## 1. Загрузка кода на сервер

**С вашего ПК (Windows, из каталога проекта):**

```powershell
# Замените IP и путь
scp -r C:\laragon\www\newsystem root@YOUR_SERVER_IP:/opt/delayu-src
```

На сервере:

```bash
sudo rsync -a --delete /opt/delayu-src/ /opt/delayu/
sudo chown -R delayu:delayu /opt/delayu
```

Или через git (если репозиторий уже на GitHub/GitLab):

```bash
sudo mkdir -p /opt/delayu
sudo useradd --system --home-dir /opt/delayu --shell /bin/bash delayu 2>/dev/null || true
sudo git clone YOUR_REPO_URL /opt/delayu
sudo chown -R delayu:delayu /opt/delayu
```

---

## 2. Первичная настройка сервера (один раз)

```bash
cd /opt/delayu
sudo DOMAIN=uzhv.example.ru bash deploy/install-server.sh
```

Без домена (доступ по IP):

```bash
sudo bash deploy/install-server.sh
```

Скрипт установит PostgreSQL, nginx, Python, создаст БД и файл `/opt/delayu/.db-credentials`.

---

## 3. Конфигурация `.env`

```bash
sudo -u delayu nano /opt/delayu/deploy/env.production.example
# Заполните DOMAIN, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, SMTP
```

Минимум для prod:

```env
DEBUG=false
DOMAIN=uzhv.example.ru
ALLOWED_HOSTS=uzhv.example.ru
CSRF_TRUSTED_ORIGINS=https://uzhv.example.ru
DELAYU_DEMO_MODE=false
DELAYU_TELEGRAM_DEMO_LOG=false
```

---

## 4. Деплой приложения

```bash
sudo -u delayu bash /opt/delayu/deploy/deploy-app.sh
```

Скрипт: venv → migrate → collectstatic → systemd → nginx → cron.

---

## 5. Администратор и данные УЖВ

```bash
sudo -u delayu bash -c 'cd /opt/delayu && .venv/bin/python manage.py createsuperuser'
sudo -u delayu bash -c 'cd /opt/delayu && .venv/bin/python manage.py seed_uzhv'
sudo -u delayu bash -c 'cd /opt/delayu && .venv/bin/python manage.py sync_uzhv_role_permissions'
sudo -u delayu bash -c 'cd /opt/delayu && .venv/bin/python manage.py setup_free_integrations'
```

После seed для prod **смените пароли** demo-пользователей или не используйте seed на боевом контуре с реальными ПДн.

---

## 6. HTTPS

DNS: A-запись домена → IP сервера.

```bash
sudo certbot --nginx -d uzhv.example.ru
```

В `.env` включите HSTS (опционально, после проверки сайта):

```env
SECURE_HSTS_SECONDS=31536000
```

Перезапуск:

```bash
sudo systemctl restart delayu
```

---

## 7. Проверка

```bash
sudo systemctl status delayu
curl -I http://127.0.0.1:8000/auth/login/
sudo tail -f /opt/delayu/logs/gunicorn-error.log
```

В браузере: `https://uzhv.example.ru/auth/login/`

---

## Обновление версии

```bash
# загрузить новый код (rsync/git pull)
sudo -u delayu bash /opt/delayu/deploy/deploy-app.sh
```

---

## Полезные команды

| Действие | Команда |
|----------|---------|
| Логи приложения | `sudo journalctl -u delayu -f` |
| Перезапуск | `sudo systemctl restart delayu` |
| Бэкап вручную | `sudo -u delayu bash /opt/delayu/deploy/backup.sh` |
| Cron-лог | `tail -f /opt/delayu/logs/cron.log` |

---

## Файлы в репозитории

```
deploy/
  install-server.sh      # bootstrap Ubuntu
  deploy-app.sh          # migrate + gunicorn + nginx
  backup.sh              # pg_dump + media
  env.production.example
  nginx/
  systemd/delayu.service
  cron/delayu
```
