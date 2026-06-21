#!/usr/bin/env bash
# Запуск только от root: sudo /opt/delayu/deploy/webhook-run.sh
# (gunicorn user delayu → sudoers NOPASSWD)
set -euo pipefail

APP_DIR="/opt/delayu"
LOG="${APP_DIR}/logs/deploy-webhook.log"
LOCK="/tmp/delayu-deploy.lock"

mkdir -p "${APP_DIR}/logs"
exec >>"${LOG}" 2>&1
echo "=== $(date -Is) deploy start pid=$$ ==="

(
  flock -n 9 || {
    echo "deploy already running, skip"
    exit 0
  }

  cd "${APP_DIR}"
  sudo -u delayu git config --global --add safe.directory "${APP_DIR}"
  sudo -u delayu git pull --ff-only origin main
  bash "${APP_DIR}/deploy/deploy-app.sh"
  sudo -u delayu bash -c "cd '${APP_DIR}' && .venv/bin/python manage.py link_superusers"
  systemctl is-active delayu
  echo "=== $(date -Is) deploy done ==="
) 9>"${LOCK}"
