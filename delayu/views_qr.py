"""QR-коды для быстрого перехода к карточкам и публичной форме."""
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_GET

from delayu.models import Subsystem
from delayu.services.qr_codes import qr_svg_for_url
from delayu.services.uzhv_qr import UZHV_QR_ENTITIES, model_for_entity


def _qr_svg_response(request, path: str) -> HttpResponse:
    url = request.build_absolute_uri(path)
    return HttpResponse(qr_svg_for_url(url), content_type="image/svg+xml")


@login_required
@require_GET
def uzhv_qr(request, entity: str, pk: int):
    if entity not in UZHV_QR_ENTITIES:
        raise Http404
    from delayu.menu import get_active_membership

    mem = get_active_membership(request.user)
    model = model_for_entity(entity)
    list_path = UZHV_QR_ENTITIES[entity][1]
    sub = mem.subsystem
    if entity in ("prescriptions", "admin-protocols"):
        get_object_or_404(model, pk=pk, inspection__subsystem=sub)
    else:
        get_object_or_404(model, pk=pk, subsystem=sub)
    return _qr_svg_response(request, f"{list_path}?open={pk}")


@login_required
@require_GET
def uzhv_qr_citizen(request, pk: int):
    return uzhv_qr(request, "citizens", pk)


@login_required
@require_GET
def uzhv_qr_appeal(request, pk: int):
    return uzhv_qr(request, "appeals", pk)


@login_required
@require_GET
def uzhv_qr_case(request, pk: int):
    return uzhv_qr(request, "cases", pk)


@login_required
@require_GET
def uzhv_qr_public_appeal(request, subsystem_code: str):
    from delayu.menu import get_active_membership

    mem = get_active_membership(request.user)
    sub = get_object_or_404(Subsystem, code=subsystem_code)
    if mem.subsystem_id != sub.pk:
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied
    path = reverse("uzhv-public-appeal", args=[sub.code])
    return _qr_svg_response(request, path)
