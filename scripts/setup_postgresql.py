"""
Создание БД и пользователя newsystem в локальном PostgreSQL.
Запуск: .venv\\Scripts\\python scripts\\setup_postgresql.py
"""
from __future__ import annotations

import getpass
import os
import sys

try:
    import psycopg
except ImportError:
    print("Установите зависимости: pip install -r requirements.txt")
    sys.exit(1)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_NAME = os.getenv("POSTGRES_DB", "newsystem")
DB_USER = os.getenv("POSTGRES_USER", "newsystem")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "newsystem")
DB_HOST = os.getenv("POSTGRES_HOST", "127.0.0.1")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
ADMIN_USER = os.getenv("POSTGRES_ADMIN_USER", "postgres")


def main() -> int:
    admin_password = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.getenv("POSTGRES_ADMIN_PASSWORD")
        or getpass.getpass(f"Пароль PostgreSQL «{ADMIN_USER}»: ")
    )

    print(f"Подключение к {DB_HOST}:{DB_PORT}...")
    try:
        conn = psycopg.connect(
            dbname="postgres",
            user=ADMIN_USER,
            password=admin_password,
            host=DB_HOST,
            port=DB_PORT,
            connect_timeout=8,
            autocommit=True,
        )
    except Exception as exc:
        print(f"Ошибка: {exc}")
        print("Проверьте службу postgresql-x64-18 и пароль пользователя postgres.")
        return 1

    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (DB_USER,))
        if not cur.fetchone():
            cur.execute(
                f'CREATE ROLE "{DB_USER}" WITH LOGIN PASSWORD %s CREATEDB',
                (DB_PASS,),
            )
            print(f"Пользователь {DB_USER} создан.")
        else:
            cur.execute(f'ALTER ROLE "{DB_USER}" WITH PASSWORD %s', (DB_PASS,))
            print(f"Пользователь {DB_USER} обновлён.")

        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
        if not cur.fetchone():
            cur.execute(
                f'CREATE DATABASE "{DB_NAME}" OWNER "{DB_USER}" ENCODING \'UTF8\' TEMPLATE template0'
            )
            print(f"База {DB_NAME} создана.")
        else:
            print(f"База {DB_NAME} уже есть.")

    conn.close()

    test = psycopg.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT,
    )
    test.close()
    print(f"Проверка {DB_USER}@{DB_NAME} — OK.")

    env_path = os.path.join(ROOT, ".env")
    example = os.path.join(ROOT, ".env.example")
    if not os.path.isfile(env_path) and os.path.isfile(example):
        with open(example, encoding="utf-8") as f:
            content = f.read()
        with open(env_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        print(f"Создан {env_path} из .env.example")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
