"""Включить CREATE EXTENSION vector (только postgres superuser)."""
from __future__ import annotations

import getpass
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "setup-pgvector.log"
PG_ROOT = Path(os.getenv("PGROOT", r"C:\Program Files\PostgreSQL\18"))


def log(msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.is_file():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


def main() -> int:
    load_dotenv()
    password = os.getenv("POSTGRES_ADMIN_PASSWORD", "")
    for arg in sys.argv[1:]:
        if arg.startswith("--admin-password="):
            password = arg.split("=", 1)[1]
    if not password:
        password = getpass.getpass("Пароль пользователя postgres: ")

    db = os.getenv("POSTGRES_DB", "newsystem")
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("POSTGRES_PORT", "5432")
    psql = PG_ROOT / "bin" / "psql.exe"
    if not psql.is_file():
        log(f"Не найден {psql}")
        return 1

    env = os.environ.copy()
    env["PGPASSWORD"] = password
    cmd = [
        str(psql),
        "-h",
        host,
        "-p",
        port,
        "-U",
        os.getenv("POSTGRES_ADMIN_USER", "postgres"),
        "-d",
        db,
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        "CREATE EXTENSION IF NOT EXISTS vector;",
        "-c",
        "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';",
    ]
    log(f"CREATE EXTENSION vector в базе {db} …")
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.stdout:
        log(result.stdout.strip())
    if result.returncode != 0:
        log("ОШИБКА:")
        log(result.stderr.strip() or "неверный пароль postgres или нет прав")
        return 1

    py = ROOT / ".venv" / "Scripts" / "python.exe"
    if py.is_file():
        subprocess.run(
            [str(py), str(ROOT / "manage.py"), "enable_pgvector", "--rebuild", "--subsystem=pilot"],
            cwd=ROOT,
        )
    log("Готово: pgvector включён.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
