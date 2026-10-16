#!/usr/bin/env bash
# Локальная модель для чата поддержки УЖВ. На стенде 1.5 ГБ ОЗУ, поэтому
# ставится маленькая модель с коротким контекстом и двумя воркерами gunicorn.
# Не печатает секреты. Сбой не должен ронять деплой.
set -u

APP_DIR="${1:-/opt/delayu}"
if [[ "${APP_DIR}" == "--warmup" ]]; then
  APP_DIR="/opt/delayu"
  MODE="warmup"
else
  MODE="${2:-install}"
fi
ENV_FILE="${APP_DIR}/.env"
WORKERS_FILE="${APP_DIR}/.support-llm-workers"

say() { echo "support-llm: $*"; }

warmup() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    exit 0
  fi
  set -a
  # shellcheck disable=SC1091
  source "${ENV_FILE}"
  set +a
  model="${DELAYU_LLM_MODEL:-}"
  if [[ -z "${model}" || "${DELAYU_LLM_BASE_URL:-}" != http://127.0.0.1:11434/v1 ]]; then
    exit 0
  fi
  if ! curl -sf -m 2 http://127.0.0.1:11434/api/tags >/dev/null; then
    systemctl start ollama || true
  fi
  say "прогрев ${model}"
  curl -sS -m 180 http://127.0.0.1:11434/api/generate \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"${model}\",\"prompt\":\"ok\",\"stream\":false,\"options\":{\"num_predict\":1,\"num_ctx\":2048}}" \
    >/dev/null || say "прогрев пропущен"
  exit 0
}

if [[ "${MODE}" == "--warmup" || "${1:-}" == "--warmup" ]]; then
  warmup
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  say "нет ${ENV_FILE}, модель не включаю"
  exit 0
fi

mem_kb="$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)"
avail_kb="$(awk '/MemAvailable/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)"
free_kb="$(df -Pk "${APP_DIR}" | awk 'NR==2 {print $4}')"
say "ram=${mem_kb}k available=${avail_kb}k disk=${free_kb}k"

if [[ "${mem_kb}" -lt 1200000 || "${free_kb}" -lt 1200000 ]]; then
  say "мало памяти или диска, модель не ставлю"
  exit 0
fi

RUN_NAME=""
if [[ "${mem_kb}" -ge 8000000 && "${free_kb}" -ge 6000000 ]]; then
  BASE_MODEL="qwen2.5:7b"
elif [[ "${mem_kb}" -ge 4500000 && "${free_kb}" -ge 3000000 ]]; then
  BASE_MODEL="qwen2.5:3b"
elif [[ "${mem_kb}" -ge 2500000 && "${free_kb}" -ge 1800000 ]]; then
  BASE_MODEL="qwen2.5:1.5b"
else
  BASE_MODEL="qwen2.5:0.5b"
  RUN_NAME="delayu-uzhv"
fi

if ! command -v ollama >/dev/null 2>&1; then
  say "устанавливаю Ollama"
  curl -fsSL https://ollama.com/install.sh | sh || { say "установка Ollama не удалась"; exit 0; }
fi

drop_in="/etc/systemd/system/ollama.service.d/delayu.conf"
if [[ ! -f "${drop_in}" ]]; then
  mkdir -p /etc/systemd/system/ollama.service.d
  cat > "${drop_in}" <<'EOF'
[Service]
Environment=OLLAMA_HOST=127.0.0.1:11434
Environment=OLLAMA_KEEP_ALIVE=30m
Environment=OLLAMA_NUM_PARALLEL=1
Environment=OLLAMA_MAX_LOADED_MODELS=1
EOF
  systemctl daemon-reload || true
fi

systemctl enable ollama >/dev/null 2>&1 || true
if ! systemctl is-active --quiet ollama; then
  systemctl start ollama || { say "служба Ollama не запустилась"; exit 0; }
fi

ready=0
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do
  if curl -sf -m 2 http://127.0.0.1:11434/api/tags >/dev/null; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "${ready}" -ne 1 ]]; then
  say "Ollama не слушает 127.0.0.1:11434"
  exit 0
fi

say "загружаю ${BASE_MODEL}"
ollama pull "${BASE_MODEL}" || { say "не удалось скачать ${BASE_MODEL}"; exit 0; }

MODEL="${BASE_MODEL}"
if [[ -n "${RUN_NAME}" ]]; then
  modelfile="${APP_DIR}/logs/delayu-uzhv.Modelfile"
  mkdir -p "${APP_DIR}/logs"
  cat > "${modelfile}" <<EOF
FROM ${BASE_MODEL}
PARAMETER num_ctx 2048
PARAMETER temperature 0.2
EOF
  ollama create "${RUN_NAME}" -f "${modelfile}" || { say "не удалось собрать ${RUN_NAME}"; exit 0; }
  rm -f "${modelfile}"
  MODEL="${RUN_NAME}"
  printf '2\n' > "${WORKERS_FILE}"
fi

SUPPORT_LLM_MODEL="${MODEL}" "${APP_DIR}/.venv/bin/python" - "${ENV_FILE}" <<'PY'
import sys
from pathlib import Path

path, model = Path(sys.argv[1]), __import__("os").environ["SUPPORT_LLM_MODEL"]
text = path.read_text(encoding="utf-8")
rows = text.splitlines()
values = {}
for line in rows:
    if not line or line.lstrip().startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip().strip('"').strip("'")

base = values.get("DELAYU_LLM_BASE_URL", "")
key = values.get("DELAYU_LLM_API_KEY", "")
openai = (not base) or ("api.openai.com" in base)
local = "127.0.0.1:11434" in base or "localhost:11434" in base
if key and not local:
    sys.exit(0)
if base and not openai and not local:
    sys.exit(0)

wanted = {
    "DELAYU_LLM_BASE_URL": "http://127.0.0.1:11434/v1",
    "DELAYU_LLM_API_KEY": "ollama",
    "DELAYU_LLM_MODEL": model,
    "DELAYU_LLM_MODEL_DEMO": model,
}
seen = set()
out = []
for line in rows:
    if "=" in line and not line.lstrip().startswith("#"):
        name = line.split("=", 1)[0].strip()
        if name in wanted:
            out.append(f"{name}={wanted[name]}")
            seen.add(name)
            continue
    out.append(line)
for name, value in wanted.items():
    if name not in seen:
        out.append(f"{name}={value}")
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY

say "модель ${MODEL} включена для чата поддержки"
