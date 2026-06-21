#!/usr/bin/env bash
# Первичная настройка Ubuntu 24.04 LTS для ДелаЮ / АИС УЖВ.
# Запуск из каталога проекта: sudo bash deploy/install-server.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_USER="${APP_USER:-delayu}"
APP_DIR="${APP_DIR:-/opt/delayu}"
DOMAIN="${DOMAIN:-}"

DB_NAME="${POSTGRES_DB:-delayu}"
DB_USER="${POSTGRES_USER:-delayu}"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Запустите от root: sudo bash $0"
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

echo "==> Обновление пакетов"
apt-get update -qq
apt-get upgrade -y -qq

echo "==> Базовые зависимости"
apt-get install -y -qq \
  python3 python3-venv python3-dev python3-pip \
  build-essential libpq-dev \
  postgresql postgresql-contrib postgresql-client \
  postgresql-16-pgvector \
  nginx certbot python3-certbot-nginx \
  git rsync curl ufw fail2ban \
  libjpeg-dev zlib1g-dev libxml2-dev libxslt1-dev

echo "==> Пользователь приложения: ${APP_USER}"
if ! id "${APP_USER}" &>/dev/null; then
  useradd --system --create-home --home-dir "${APP_DIR}" --shell /bin/bash "${APP_USER}"
fi
mkdir -p "${APP_DIR}"
chown "${APP_USER}:${APP_USER}" "${APP_DIR}"

echo "==> PostgreSQL: БД ${DB_NAME}, пользователь ${DB_USER}"
DB_PASS="$(openssl rand -base64 24 | tr -d '/+=' | head -c 32)"
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASS}';
  END IF;
END
\$\$;
SELECT 'CREATE DATABASE ${DB_NAME} OWNER ${DB_USER}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_NAME}')\gexec
SQL
sudo -u postgres psql -d "${DB_NAME}" -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS vector;"

CREDS_FILE="${APP_DIR}/.db-credentials"
cat > "${CREDS_FILE}" <<EOF
POSTGRES_DB=${DB_NAME}
POSTGRES_USER=${DB_USER}
POSTGRES_PASSWORD=${DB_PASS}
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
EOF
chown "${APP_USER}:${APP_USER}" "${CREDS_FILE}"
chmod 600 "${CREDS_FILE}"
echo "    Пароль БД: ${CREDS_FILE} (только пользователь ${APP_USER})"

echo "==> UFW"
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable

echo "==> Копирование deploy-файлов в ${APP_DIR}"
rsync -a --exclude='.venv' --exclude='media' --exclude='staticfiles' \
  "${SCRIPT_DIR}/../" "${APP_DIR}/" 2>/dev/null || \
  cp -a "${SCRIPT_DIR}/.." "${APP_DIR}/" 2>/dev/null || true
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

echo ""
echo "=============================================="
echo " Сервер подготовлен."
echo " 1) Если код ещё не в ${APP_DIR} — загрузите (git clone / rsync)"
echo " 2) sudo -u ${APP_USER} bash ${APP_DIR}/deploy/deploy-app.sh"
echo " 3) Пароль БД: ${APP_DIR}/.db-credentials"
echo "=============================================="
