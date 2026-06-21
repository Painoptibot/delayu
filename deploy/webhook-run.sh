#!/usr/bin/env bash
# Webhook: фоновый деплой с lock и логом. Запуск: sudo /opt/delayu/deploy/webhook-run.sh
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
  bash "${APP_DIR}/deploy/run-deploy.sh"
  echo "=== $(date -Is) deploy done ==="
) 9>"${LOCK}"
