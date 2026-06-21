"""Webhook автодеплоя (GitHub Actions → HTTPS, без inbound SSH)."""

from __future__ import annotations

import logging
import secrets
import subprocess

from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

WEBHOOK_SCRIPT = "/opt/delayu/deploy/webhook-run.sh"


@csrf_exempt
@require_POST
def deploy_webhook(request):
    expected = (getattr(settings, "DEPLOY_WEBHOOK_TOKEN", "") or "").strip()
    if not expected:
        return HttpResponseForbidden("deploy webhook disabled")

    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        provided = auth[7:].strip()
    else:
        provided = (request.headers.get("X-Deploy-Token") or "").strip()

    if not provided or not secrets.compare_digest(provided, expected):
        return HttpResponseForbidden("invalid token")

    try:
        subprocess.Popen(
            ["/usr/bin/sudo", "-n", WEBHOOK_SCRIPT],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        logger.exception("deploy webhook failed to start")
        return JsonResponse({"status": "error", "detail": str(exc)}, status=500)

    return JsonResponse({"status": "accepted"})
