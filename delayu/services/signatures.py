"""#37 — запросы на подписание КЭП."""
from django.utils import timezone

from delayu.models import SignatureRequest
from delayu.services.documents import sign_document


def create_signature_request(*, document, requester, provider: str = "mock") -> SignatureRequest:
    return SignatureRequest.objects.create(
        document=document,
        requester=requester,
        provider=provider,
        status=SignatureRequest.Status.PENDING,
        meta={"document_title": document.title},
    )


def send_to_signing(req: SignatureRequest) -> SignatureRequest:
    """Mock-адаптер: имитация отправки во внешний сервис КЭП."""
    if req.document.is_signed:
        req.status = SignatureRequest.Status.REJECTED
        req.error_text = "Документ уже подписан"
        req.completed_at = timezone.now()
        req.save()
        return req
    req.status = SignatureRequest.Status.SENT
    req.external_id = req.external_id or f"KEP-{req.pk}"
    req.meta = {**(req.meta or {}), "sent_at": timezone.now().isoformat()}
    req.save(update_fields=["status", "external_id", "meta"])
    return req


def complete_signature(req: SignatureRequest, *, user) -> SignatureRequest:
    """Завершить подписание (mock: локальная подпись)."""
    try:
        send_to_signing(req)
        sign_document(req.document, user)
        req.status = SignatureRequest.Status.SIGNED
        req.error_text = ""
        req.completed_at = timezone.now()
        req.meta = {**(req.meta or {}), "signed_via": req.provider}
        req.save()
    except ValueError as exc:
        req.status = SignatureRequest.Status.FAILED
        req.error_text = str(exc)
        req.completed_at = timezone.now()
        req.save()
    return req
