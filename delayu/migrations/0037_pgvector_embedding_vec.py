from django.db import migrations


def enable_pgvector(apps, schema_editor):
    from delayu.services.pgvector_search import ensure_pgvector_schema

    ensure_pgvector_schema()


def disable_pgvector(apps, schema_editor):
    from django.db import connection

    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute("DROP INDEX IF EXISTS delayu_searchindexentry_embedding_vec_idx")
        cursor.execute(
            """
            ALTER TABLE delayu_searchindexentry
            DROP COLUMN IF EXISTS embedding_vec
            """
        )


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("delayu", "0036_searchindexentry_embedding"),
    ]

    operations = [
        migrations.RunPython(enable_pgvector, disable_pgvector),
    ]
