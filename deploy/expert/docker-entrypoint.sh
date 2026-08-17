#!/bin/sh
set -e

echo "[delayu-expert] ожидание PostgreSQL (${POSTGRES_HOST:-db}:${POSTGRES_PORT:-5432})..."
python - <<'PY'
import os, socket, time
host = os.environ.get("POSTGRES_HOST", "db")
port = int(os.environ.get("POSTGRES_PORT", "5432"))
deadline = time.time() + 90
while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=2):
            print("[delayu-expert] PostgreSQL доступен")
            break
    except OSError:
        time.sleep(1)
else:
    raise SystemExit("[delayu-expert] PostgreSQL недоступен")
PY

echo "[delayu-expert] миграции..."
python manage.py migrate --noinput

echo "[delayu-expert] статика..."
python manage.py collectstatic --noinput

if [ "${DELAYU_SEED_ON_START:-1}" = "1" ]; then
  echo "[delayu-expert] демо-данные для экспертизы..."
  python manage.py seed_registry_demo || true
fi

echo "[delayu-expert] запуск: $*"
exec "$@"
