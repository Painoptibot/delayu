#!/usr/bin/env bash
# Первичная настройка git на VPS для деплоя через git pull.
# Запуск от root на сервере:
#   sudo bash deploy/setup-git-prod.sh https://github.com/USER/newsystem.git
#
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/delayu}"
REPO_URL="${1:-}"

if [[ -z "${REPO_URL}" ]]; then
  echo "Использование: sudo bash deploy/setup-git-prod.sh <git-url>"
  echo "Пример: sudo bash deploy/setup-git-prod.sh https://github.com/you/newsystem.git"
  exit 1
fi

echo "==> Git deploy: ${APP_DIR}"
echo "    Remote: ${REPO_URL}"

if [[ ! -d "${APP_DIR}" ]]; then
  mkdir -p "${APP_DIR}"
  chown delayu:delayu "${APP_DIR}"
fi

if [[ ! -d "${APP_DIR}/.git" ]]; then
  echo "==> git init + remote"
  sudo -u delayu git -C "${APP_DIR}" init
  sudo -u delayu git -C "${APP_DIR}" remote add origin "${REPO_URL}" 2>/dev/null \
    || sudo -u delayu git -C "${APP_DIR}" remote set-url origin "${REPO_URL}"
  sudo -u delayu git -C "${APP_DIR}" config user.email "deploy@delau.tech"
  sudo -u delayu git -C "${APP_DIR}" config user.name "Delayu Deploy"
else
  sudo -u delayu git -C "${APP_DIR}" remote set-url origin "${REPO_URL}"
fi

echo "==> fetch (нужен доступ: SSH-ключ deploy или HTTPS token)"
sudo -u delayu git -C "${APP_DIR}" fetch origin || {
  echo ""
  echo "!!! Не удалось fetch. Настройте доступ:"
  echo "  SSH: ssh-keygen -t ed25519 -f /home/delayu/.ssh/id_ed25519 -N ''"
  echo "       cat /home/delayu/.ssh/id_ed25519.pub  → Deploy key в GitHub"
  echo "  HTTPS: git remote set-url origin https://TOKEN@github.com/USER/REPO.git"
  exit 1
}

BRANCH="${DEPLOY_BRANCH:-main}"
if ! sudo -u delayu git -C "${APP_DIR}" show-ref --verify --quiet "refs/remotes/origin/${BRANCH}"; then
  BRANCH=master
fi

echo "==> checkout origin/${BRANCH}"
sudo -u delayu git -C "${APP_DIR}" checkout -B "${BRANCH}" "origin/${BRANCH}" 2>/dev/null \
  || sudo -u delayu git -C "${APP_DIR}" pull origin "${BRANCH}"

echo "==> deploy"
if [[ "$(id -u)" -eq 0 ]]; then
  bash "${APP_DIR}/deploy/update-prod.sh"
else
  sudo bash "${APP_DIR}/deploy/update-prod.sh"
fi

echo ""
echo "Готово. Дальнейшие обновления:"
echo "  cd ${APP_DIR} && sudo bash deploy/update-prod.sh"
