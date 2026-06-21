import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection
from delayu.services.pgvector_search import pgvector_available, ensure_pgvector_schema

print("DB vendor:", connection.vendor)
print("pgvector_available:", pgvector_available())

with connection.cursor() as c:
    try:
        c.execute("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector'")
        print("pg_extension:", c.fetchall())
    except Exception as e:
        print("pg_extension error:", e)
    try:
        c.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'delayu_searchindexentry' AND column_name = 'embedding_vec'"
        )
        print("embedding_vec column:", c.fetchall())
    except Exception as e:
        print("column check error:", e)

print("ensure_pgvector_schema:", ensure_pgvector_schema())
print("pgvector_available after ensure:", pgvector_available())
