#!/usr/bin/env bash
# Резервная копия PostgreSQL + media (хранить 7 последних дампов).
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/delayu}"
BACKUP_DIR="${APP_DIR}/backups"
KEEP=7

mkdir -p "${BACKUP_DIR}"
# shellcheck disable=SC1091
set -a && source "${APP_DIR}/.env" && set +a

STAMP="$(date +%Y%m%d_%H%M%S)"
DUMP="${BACKUP_DIR}/db_${STAMP}.sql.gz"

PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump \
  -h "${POSTGRES_HOST:-127.0.0.1}" \
  -U "${POSTGRES_USER}" \
  -d "${POSTGRES_DB}" \
  | gzip > "${DUMP}"

if [[ -d "${APP_DIR}/media" ]]; then
  tar -czf "${BACKUP_DIR}/media_${STAMP}.tar.gz" -C "${APP_DIR}" media
fi

ls -1t "${BACKUP_DIR}"/db_*.sql.gz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
ls -1t "${BACKUP_DIR}"/media_*.tar.gz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f

echo "$(date -Is) backup ok: ${DUMP}"
