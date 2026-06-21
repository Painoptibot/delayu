#!/usr/bin/env bash
# Cron: подтянуть main с GitHub, если появились коммиты (без inbound с GitHub).
# Установка: строка в /etc/cron.d/delayu (см. deploy/cron/delayu)
set -euo pipefail

APP_DIR="/opt/delayu"
LOG="${APP_DIR}/logs/cron-deploy.log"

{
  echo "=== $(date -Is) cron check ==="
  cd "${APP_DIR}"
  sudo -u delayu git fetch origin main
  LOCAL=$(sudo -u delayu git rev-parse HEAD)
  REMOTE=$(sudo -u delayu git rev-parse origin/main)
  if [[ "${LOCAL}" != "${REMOTE}" ]]; then
    echo "new commits ${LOCAL:0:7} -> ${REMOTE:0:7}, deploying"
    bash "${APP_DIR}/deploy/webhook-run.sh"
  else
    echo "up to date ${LOCAL:0:7}"
  fi
} >>"${LOG}" 2>&1
