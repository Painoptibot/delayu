#!/usr/bin/env bash
# Быстрое обновление prod после git pull или загрузки файлов.
# Запуск от root (нужен sudo для systemd/nginx) или от delayu (без nginx reload).
#
#   cd /opt/delayu && sudo bash deploy/update-prod.sh
#
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "${APP_DIR}"

echo "==> Обновление prod: ${APP_DIR}"

if [[ -d "${APP_DIR}/.git" ]]; then
  echo "==> git pull"
  sudo -u delayu git -C "${APP_DIR}" pull --ff-only
fi

if [[ "$(id -u)" -eq 0 ]]; then
  sudo -u delayu bash "${APP_DIR}/deploy/deploy-app.sh"
else
  bash "${APP_DIR}/deploy/deploy-app.sh"
fi

echo "==> Superuser → УЖВ (если нужно)"
sudo -u delayu bash -c "cd '${APP_DIR}' && .venv/bin/python manage.py link_superusers"

echo "==> Проверка главной (superuser)"
sudo -u delayu bash -c "cd '${APP_DIR}' && .venv/bin/python manage.py verify_platform --username dalayu" || true

echo ""
echo "Готово: https://${DOMAIN:-delau.tech}/"
