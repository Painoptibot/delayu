#!/usr/bin/env bash
# Деплой prod (git pull + migrate + restart). Запуск от root:
#   sudo bash /opt/delayu/deploy/run-deploy.sh
set -euo pipefail

APP_DIR="/opt/delayu"
cd "${APP_DIR}"

sudo -u delayu git config --global --add safe.directory "${APP_DIR}"
sudo -u delayu git fetch origin main
sudo -u delayu git checkout -B main origin/main
bash "${APP_DIR}/deploy/deploy-app.sh"
sudo -u delayu bash -c "cd '${APP_DIR}' && .venv/bin/python manage.py link_superusers"
systemctl is-active delayu
