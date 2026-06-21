from django.http import JsonResponse


def health(request):
    """Проверка, что Django и БД доступны."""
    from django.db import connection

    db_ok = False
    try:
        connection.ensure_connection()
        db_ok = True
    except Exception:
        pass

    return JsonResponse(
        {
            "status": "ok" if db_ok else "degraded",
            "service": "newsystem",
            "database": "connected" if db_ok else "unavailable",
        }
    )
