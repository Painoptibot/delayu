"""
Reset PostgreSQL superuser password via temporary trust in pg_hba.conf.

Data dir (Laragon): C:\\laragon\\www\\postgres
"""
from __future__ import annotations

import getpass
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PG_BIN = Path(os.getenv("PGROOT", r"C:\Program Files\PostgreSQL\18")) / "bin"
PG_DATA = Path(os.getenv("PGDATA", r"C:\laragon\www\postgres"))
HBA = PG_DATA / "pg_hba.conf"
SERVICE = os.getenv("POSTGRES_SERVICE", "postgresql-x64-18")


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print(">", " ".join(cmd))
    return subprocess.run(cmd, **kwargs)


def backup_hba() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = HBA.with_suffix(f".conf.bak.{stamp}")
    shutil.copy2(HBA, backup)
    print(f"Backup: {backup}")
    return backup


def set_trust_mode(enabled: bool) -> None:
    text = HBA.read_text(encoding="utf-8")
    if enabled:
        new = re.sub(
            r"^(local\s+all\s+all\s+)scram-sha-256\s*$",
            r"\1trust",
            text,
            flags=re.MULTILINE,
        )
        new = re.sub(
            r"^(host\s+all\s+all\s+127\.0\.0\.1/32\s+)scram-sha-256\s*$",
            r"\1trust",
            new,
            flags=re.MULTILINE,
        )
        new = re.sub(
            r"^(host\s+all\s+all\s+::1/128\s+)scram-sha-256\s*$",
            r"\1trust",
            new,
            flags=re.MULTILINE,
        )
    else:
        new = re.sub(
            r"^(local\s+all\s+all\s+)trust\s*$",
            r"\1scram-sha-256",
            text,
            flags=re.MULTILINE,
        )
        new = re.sub(
            r"^(host\s+all\s+all\s+127\.0\.0\.1/32\s+)trust\s*$",
            r"\1scram-sha-256",
            new,
            flags=re.MULTILINE,
        )
        new = re.sub(
            r"^(host\s+all\s+all\s+::1/128\s+)trust\s*$",
            r"\1scram-sha-256",
            new,
            flags=re.MULTILINE,
        )
    HBA.write_text(new, encoding="utf-8")


def reload_postgres() -> None:
    pg_ctl = PG_BIN / "pg_ctl.exe"
    result = run([str(pg_ctl), "reload", "-D", str(PG_DATA)], capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr or result.stdout)
        print("Trying service restart …")
        run(["net", "stop", SERVICE], capture_output=True)
        run(["net", "start", SERVICE], capture_output=True)


def alter_postgres_password(new_password: str) -> None:
    psql = PG_BIN / "psql.exe"
    sql = f"ALTER USER postgres WITH PASSWORD '{new_password.replace(chr(39), chr(39)+chr(39))}';"
    result = run(
        [str(psql), "-h", "127.0.0.1", "-U", "postgres", "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr or result.stdout or "ALTER USER failed")
    print(result.stdout or "Password updated.")


def main() -> int:
    if not HBA.is_file():
        print(f"pg_hba.conf not found: {HBA}")
        return 1

    new_password = os.getenv("NEW_POSTGRES_PASSWORD", "")
    for arg in sys.argv[1:]:
        if arg.startswith("--password="):
            new_password = arg.split("=", 1)[1]
    if not new_password:
        new_password = getpass.getpass("New password for postgres: ")
        confirm = getpass.getpass("Confirm: ")
        if new_password != confirm:
            print("Passwords do not match.")
            return 1

    backup_hba()
    try:
        set_trust_mode(True)
        reload_postgres()
        alter_postgres_password(new_password)
    finally:
        set_trust_mode(False)
        reload_postgres()

    print("")
    print("OK: postgres password changed.")
    print("Use this password for setup-pgvector-extension.bat")
    print(f"  NEW_POSTGRES_PASSWORD={new_password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
