#!/usr/bin/env bash
# Деплой/обновление приложения (запуск от пользователя delayu).
#   cd /opt/delayu && bash deploy/deploy-app.sh
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "${APP_DIR}"

VENV="${APP_DIR}/.venv"
GUNICORN_WORKERS="${GUNICORN_WORKERS:-4}"

echo "==> ДелаЮ: ${APP_DIR}"

if [[ ! -f "${APP_DIR}/manage.py" ]]; then
  echo "Ошибка: manage.py не найден. Загрузите код в ${APP_DIR}"
  exit 1
fi

echo "==> Python venv"
if [[ ! -d "${VENV}" ]]; then
  python3 -m venv "${VENV}"
fi
"${VENV}/bin/pip" install -q --upgrade pip
"${VENV}/bin/pip" install -q -r requirements.txt

if [[ ! -f "${APP_DIR}/.env" ]]; then
  if [[ -f "${APP_DIR}/.db-credentials" ]]; then
    echo "==> Создание .env из шаблона + credentials БД"
    cp deploy/env.production.example .env
    cat "${APP_DIR}/.db-credentials" >> .env
    SECRET_KEY="$("${VENV}/bin/python" -c "import secrets; print(secrets.token_urlsafe(48))")"
    sed -i "s/^SECRET_KEY=.*/SECRET_KEY=${SECRET_KEY}/" .env
    echo ""
    echo "!!! Отредактируйте .env: ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, DOMAIN, SMTP"
    echo "    nano ${APP_DIR}/.env"
    echo ""
  else
    cp deploy/env.production.example .env
    echo "Создан .env — заполните POSTGRES_* и SECRET_KEY, затем запустите скрипт снова."
    exit 1
  fi
fi

# shellcheck disable=SC1091
set -a && source "${APP_DIR}/.env" && set +a

echo "==> Миграции"
"${VENV}/bin/python" manage.py migrate --noinput

echo "==> Статика"
"${VENV}/bin/python" manage.py collectstatic --noinput

mkdir -p media logs

echo "==> systemd gunicorn"
sudo cp deploy/systemd/delayu.service /etc/systemd/system/delayu.service
sudo sed -i "s|/opt/delayu|${APP_DIR}|g" /etc/systemd/system/delayu.service
sudo sed -i "s/--workers 4/--workers ${GUNICORN_WORKERS}/" /etc/systemd/system/delayu.service
sudo systemctl daemon-reload
sudo systemctl enable delayu
sudo systemctl restart delayu

if [[ -n "${DOMAIN:-}" ]]; then
  echo "==> Nginx (${DOMAIN})"
  sudo cp deploy/nginx/delayu-http-domain.conf.template /tmp/delayu.nginx
  sudo sed -i "s/__DOMAIN__/${DOMAIN}/g" /tmp/delayu.nginx
  sudo sed -i "s|/opt/delayu|${APP_DIR}|g" /tmp/delayu.nginx
  sudo mv /tmp/delayu.nginx /etc/nginx/sites-available/delayu
  sudo ln -sf /etc/nginx/sites-available/delayu /etc/nginx/sites-enabled/delayu
  sudo rm -f /etc/nginx/sites-enabled/default
  sudo nginx -t
  sudo systemctl reload nginx
  echo "    HTTPS: sudo certbot --nginx -d ${DOMAIN}"
else
  echo "==> Nginx (IP / без домена)"
  sudo cp deploy/nginx/delayu-http.conf /etc/nginx/sites-available/delayu
  sudo sed -i "s|/opt/delayu|${APP_DIR}|g" /etc/nginx/sites-available/delayu
  sudo ln -sf /etc/nginx/sites-available/delayu /etc/nginx/sites-enabled/delayu
  sudo rm -f /etc/nginx/sites-enabled/default
  sudo nginx -t && sudo systemctl reload nginx
fi

echo "==> Cron"
sudo cp deploy/cron/delayu /etc/cron.d/delayu
sudo sed -i "s|/opt/delayu|${APP_DIR}|g" /etc/cron.d/delayu
sudo chmod 644 /etc/cron.d/delayu

echo ""
echo "==> Статус"
sudo systemctl --no-pager status delayu || true
curl -sf -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:8000/auth/login/ || true

echo ""
echo "Готово. Дальше:"
echo "  ${VENV}/bin/python manage.py createsuperuser"
echo "  ${VENV}/bin/python manage.py seed_uzhv          # если нужны демо-данные УЖВ"
echo "  ${VENV}/bin/python manage.py setup_free_integrations"
echo "  certbot --nginx -d \${DOMAIN}   # если ещё нет HTTPS"
