"""
Установка pgvector для PostgreSQL 18 на Windows.

1. Скачивает бинарники pgvector v0.8.2 (PG18, community build).
2. Копирует в каталог PostgreSQL (нужны права администратора).
3. Выполняет CREATE EXTENSION vector в базе newsystem.

Запуск:
  manage.bat setup_pgvector
  manage.bat setup_pgvector --admin-password=YOUR_POSTGRES_PASSWORD

Или двойной клик setup-pgvector.bat (запросит UAC).
"""
from __future__ import annotations

import getpass
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "scripts" / "cache"
ZIP_URL = (
    "https://github.com/andreiramani/pgvector_pgsql_windows/releases/download/"
    "0.8.2_18.0.2/vector.v0.8.2-pg18.zip"
)
ZIP_PATH = CACHE / "vector.v0.8.2-pg18.zip"
EXTRACT = CACHE / "pgvector_extract"
PG_ROOT = Path(os.getenv("PGROOT", r"C:\Program Files\PostgreSQL\18"))


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.is_file():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


def download() -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    if not ZIP_PATH.is_file():
        print(f"Скачивание pgvector → {ZIP_PATH.name} …")
        urlretrieve(ZIP_URL, ZIP_PATH)
    if EXTRACT.is_dir():
        shutil.rmtree(EXTRACT)
    with zipfile.ZipFile(ZIP_PATH) as zf:
        zf.extractall(EXTRACT)
    dll = EXTRACT / "lib" / "vector.dll"
    if not dll.is_file():
        raise SystemExit("В архиве нет lib/vector.dll")
    return EXTRACT


def install_files(src: Path) -> None:
    targets = [
        (src / "lib" / "vector.dll", PG_ROOT / "lib" / "vector.dll"),
        (src / "share" / "extension", PG_ROOT / "share" / "extension"),
        (src / "include" / "server" / "extension" / "vector", PG_ROOT / "include" / "server" / "extension" / "vector"),
    ]
    for src_path, dst in targets:
        if src_path.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
            for item in src_path.glob("vector*"):
                shutil.copy2(item, dst / item.name)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst)
    print(f"Файлы pgvector скопированы в {PG_ROOT}")


def psql_bin() -> Path:
    candidate = PG_ROOT / "bin" / "psql.exe"
    if candidate.is_file():
        return candidate
    raise SystemExit(f"Не найден psql: {candidate}")


def enable_extension(admin_password: str) -> None:
    db = os.getenv("POSTGRES_DB", "newsystem")
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("POSTGRES_PORT", "5432")
    env = os.environ.copy()
    env["PGPASSWORD"] = admin_password
    psql = psql_bin()
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
    ]
    print(f"CREATE EXTENSION vector в базе {db} …")
    result = subprocess.run(cmd, check=True, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    log_path = ROOT / "setup-pgvector.log"
    log_path.write_text((result.stdout or "") + "\n", encoding="utf-8")
    print(result.stdout or "OK")
    print("Расширение vector включено.")


def django_enable() -> None:
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    if not py.is_file():
        py = Path(sys.executable)
    subprocess.run([str(py), str(ROOT / "manage.py"), "enable_pgvector", "--rebuild", "--subsystem=pilot"], cwd=ROOT, check=False)


def write_admin_bat(admin_password: str = "") -> Path:
    bat = ROOT / "setup-pgvector-admin.bat"
    lines = [
        "@echo off",
        "chcp 65001 >nul",
        f'cd /d "{ROOT}"',
        "call .venv\\Scripts\\activate.bat",
        "echo === Установка pgvector (требуются права администратора) ===",
    ]
    if admin_password:
        lines.append(f'set POSTGRES_ADMIN_PASSWORD={admin_password}')
    lines += [
        "python scripts\\setup_pgvector.py --install-only",
        "if errorlevel 1 pause & exit /b 1",
    ]
    if not admin_password:
        lines.append("set /p POSTGRES_ADMIN_PASSWORD=Пароль postgres: ")
    lines += [
        "python scripts\\enable_pgvector_extension.py",
        "if errorlevel 1 goto failed",
        "echo.",
        "echo Готово. Проверка:",
        "python scripts\\check_pgvector.py",
        "goto end",
        ":failed",
        "echo.",
        "echo ОШИБКА — см. setup-pgvector.log",
        "type setup-pgvector.log 2>nul",
        ":end",
        "pause",
    ]
    bat.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return bat


def elevate_admin_bat(bat: Path) -> int:
    ps = (
        f'Start-Process -FilePath "{bat}" -Verb RunAs -Wait; '
        f'exit $LASTEXITCODE'
    )
    return subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        cwd=ROOT,
    ).returncode


def main() -> int:
    _load_dotenv()
    install_only = "--install-only" in sys.argv
    enable_only = "--enable-extension" in sys.argv
    admin_password = os.getenv("POSTGRES_ADMIN_PASSWORD", "")
    for arg in sys.argv[1:]:
        if arg.startswith("--admin-password="):
            admin_password = arg.split("=", 1)[1]

    src = download()
    if enable_only:
        if not admin_password:
            admin_password = getpass.getpass("Пароль пользователя postgres: ")
        try:
            enable_extension(admin_password)
        except subprocess.CalledProcessError as exc:
            err = (exc.stderr or str(exc)).strip()
            print(err)
            (ROOT / "setup-pgvector.log").write_text(err + "\n", encoding="utf-8")
            print("CREATE EXTENSION не выполнен — проверьте пароль postgres.")
            print("Запустите: setup-pgvector-extension.bat")
            return 1
        django_enable()
        return 0

    if not install_only:
        print("Подготовка установщика с правами администратора …")

    try:
        install_files(src)
    except PermissionError:
        if install_only:
            print("ОШИБКА: запустите setup-pgvector.bat от имени администратора.")
            return 1
        bat = write_admin_bat(admin_password)
        print(f"Нет прав на запись в {PG_ROOT}.")
        print("Подтвердите запрос UAC Windows для установки …")
        code = elevate_admin_bat(bat)
        if code != 0:
            print(f"Запустите вручную от администратора: {bat}")
            return code
        django_enable()
        return 0

    if install_only:
        return 0

    if not admin_password:
        admin_password = getpass.getpass("Пароль пользователя postgres: ")
    try:
        enable_extension(admin_password)
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or str(exc)).strip()
        print(err)
        (ROOT / "setup-pgvector.log").write_text(err + "\n", encoding="utf-8")
        print("CREATE EXTENSION не выполнен — проверьте пароль postgres.")
        print("Запустите: setup-pgvector-extension.bat")
        return 1

    django_enable()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
