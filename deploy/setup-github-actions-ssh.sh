#!/bin/bash
# Настройка SSH-ключа для GitHub Actions. Запуск на VPS от root:
#   sudo bash /opt/delayu/deploy/setup-github-actions-ssh.sh
set -euo pipefail

KEY="/root/.ssh/github_actions_deploy"

mkdir -p /root/.ssh
chmod 700 /root/.ssh

if [[ ! -f "${KEY}" ]]; then
  ssh-keygen -t ed25519 -f "${KEY}" -N "" -C "github-actions-deploy"
fi

touch /root/.ssh/authorized_keys
grep -qF "$(cat "${KEY}.pub")" /root/.ssh/authorized_keys \
  || cat "${KEY}.pub" >> /root/.ssh/authorized_keys

chmod 600 /root/.ssh/authorized_keys "${KEY}"

echo "=== Fingerprint (сохраните для сверки) ==="
ssh-keygen -lf "${KEY}.pub"

echo ""
echo "=== Проверка входа ключом на localhost ==="
if ssh -i "${KEY}" -o BatchMode=yes -o PasswordAuthentication=no \
     -o StrictHostKeyChecking=no root@127.0.0.1 "echo LOCAL_OK"; then
  echo "OK: ключ принят sshd"
else
  echo "FAIL: sshd не принимает ключ — проверьте PermitRootLogin / PubkeyAuthentication"
  exit 1
fi

echo ""
echo "=== GitHub secret DEPLOY_SSH_KEY — приватный ключ ниже ==="
cat "${KEY}"

echo ""
echo "=== Альтернатива: одна строка base64 → secret DEPLOY_SSH_KEY_B64 ==="
base64 -w0 "${KEY}"
echo ""
