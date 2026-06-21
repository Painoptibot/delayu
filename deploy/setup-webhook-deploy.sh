#!/usr/bin/env bash
# Однократная настройка webhook-деплоя на VPS (от root).
#   cd /opt/delayu && sudo bash deploy/setup-webhook-deploy.sh
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
ENV_FILE="${APP_DIR}/.env"

chmod +x "${APP_DIR}/deploy/webhook-run.sh"

if [[ ! -f /etc/sudoers.d/delayu-deploy ]]; then
  cp "${APP_DIR}/deploy/sudoers-delayu-deploy" /etc/sudoers.d/delayu-deploy
  chmod 440 /etc/sudoers.d/delayu-deploy
  visudo -c
  echo "==> sudoers: /etc/sudoers.d/delayu-deploy"
fi

if [[ -f "${ENV_FILE}" ]] && grep -q '^DEPLOY_WEBHOOK_TOKEN=' "${ENV_FILE}"; then
  TOKEN=$(grep '^DEPLOY_WEBHOOK_TOKEN=' "${ENV_FILE}" | cut -d= -f2-)
else
  TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
  echo "DEPLOY_WEBHOOK_TOKEN=${TOKEN}" >> "${ENV_FILE}"
  echo "==> DEPLOY_WEBHOOK_TOKEN добавлен в ${ENV_FILE}"
fi

systemctl restart delayu

DOMAIN=$(grep '^DOMAIN=' "${ENV_FILE}" 2>/dev/null | cut -d= -f2- || echo "delau.tech")
echo ""
echo "GitHub Secrets:"
echo "  DEPLOY_URL          https://${DOMAIN}"
echo "  DEPLOY_WEBHOOK_TOKEN  ${TOKEN}"
echo ""
echo "Проверка (с VPS):"
echo "  curl -fsS -X POST https://${DOMAIN}/internal/deploy/ -H \"Authorization: Bearer ${TOKEN}\""
