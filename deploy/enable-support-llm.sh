#!/usr/bin/env bash
# Поднимает локальную модель для чата поддержки УЖВ и прописывает её в .env.
# Идемпотентно. Не печатает секреты. Ошибка не должна ронять деплой: вызывающий
# скрипт запускает этот файл через «|| echo».
set -u

APP_DIR="${1:-/opt/delayu}"
ENV_FILE="${APP_DIR}/.env"

say() { echo "support-llm: $*"; }

if [[ ! -f "${ENV_FILE}" ]]; then
  say "нет ${ENV_FILE}, модель не включаю"
  exit 0
fi

mem_kb="$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)"
free_kb="$(df -Pk "${APP_DIR}" | awk 'NR==2 {print $4}')"
if [[ "${mem_kb}" -lt 1800000 || "${free_kb}" -lt 1500000 ]]; then
  say "мало памяти или диска (ram=${mem_kb}k disk=${free_kb}k), модель не ставлю"
  exit 0
fi

if [[ "${mem_kb}" -ge 8000000 && "${free_kb}" -ge 6000000 ]]; then
  MODEL="qwen2.5:7b"
elif [[ "${mem_kb}" -ge 4500000 && "${free_kb}" -ge 3000000 ]]; then
  MODEL="qwen2.5:3b"
else
  MODEL="qwen2.5:1.5b"
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
Environment=OLLAMA_KEEP_ALIVE=6h
Environment=OLLAMA_NUM_PARALLEL=1
EOF
  systemctl daemon-reload || true
  systemctl restart ollama || true
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

say "загружаю ${MODEL}"
ollama pull "${MODEL}" || { say "не удалось скачать ${MODEL}"; exit 0; }

say "прогрев ${MODEL}"
curl -sS -m 180 http://127.0.0.1:11434/api/generate \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"${MODEL}\",\"prompt\":\"ok\",\"stream\":false,\"options\":{\"num_predict\":1}}" \
  >/dev/null || say "прогрев пропущен"

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
if key or not openai:
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
