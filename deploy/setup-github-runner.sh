#!/usr/bin/env bash
# Self-hosted GitHub Actions runner на VPS (исходящее соединение к GitHub).
#
# 1) GitHub → Settings → Actions → Runners → New self-hosted runner → Linux
# 2) Скопируйте registration token (живёт ~1 час)
# 3) На VPS:
#      cd /opt/delayu && sudo bash deploy/setup-github-runner.sh ВАШ_TOKEN
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
RUNNER_DIR="${APP_DIR}/actions-runner"
RUNNER_VERSION="${RUNNER_VERSION:-2.323.0}"

if [[ $# -lt 1 ]]; then
  echo "Usage: sudo bash deploy/setup-github-runner.sh REGISTRATION_TOKEN"
  echo "Token: github.com/Painoptibot/delayu → Settings → Actions → Runners → New"
  exit 1
fi

TOKEN="$1"
REPO_URL="$(
  sudo -u delayu git -C "${APP_DIR}" remote get-url origin \
    | sed -E 's|^git@github.com:|https://github.com/|; s|\.git$||'
)"

echo "==> Repo: ${REPO_URL}"
echo "==> Runner dir: ${RUNNER_DIR}"

mkdir -p "${RUNNER_DIR}"
cd "${RUNNER_DIR}"

if [[ ! -f ./config.sh ]]; then
  ARCH="linux-x64"
  TAR="actions-runner-${ARCH}-${RUNNER_VERSION}.tar.gz"
  curl -fsSL -o "${TAR}" "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${TAR}"
  tar xzf "${TAR}"
  rm -f "${TAR}"
fi

chown -R delayu:delayu "${RUNNER_DIR}"

sudo -u delayu ./config.sh \
  --url "${REPO_URL}" \
  --token "${TOKEN}" \
  --name "delayu-vps" \
  --labels "delayu,linux,self-hosted" \
  --unattended \
  --replace

./svc.sh install delayu
./svc.sh start

echo ""
echo "Runner установлен. Проверка:"
echo "  GitHub → Settings → Actions → Runners — должен быть Online (delayu-vps)"
echo "  systemctl status 'actions.runner.*'"
