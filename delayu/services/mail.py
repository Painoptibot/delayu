"""Отправка и приём почты (SMTP/IMAP) для подсистем."""
from __future__ import annotations

import email
import imaplib
import logging
from email.header import decode_header
from email.utils import parseaddr

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.utils import timezone

from delayu.models import Correspondence, MailDeliveryLog, MailTransportConfig

logger = logging.getLogger("delayu.mail")


def get_or_create_transport(subsystem) -> MailTransportConfig:
    cfg, _ = MailTransportConfig.objects.get_or_create(subsystem=subsystem)
    return cfg


def transport_is_ready(cfg: MailTransportConfig) -> bool:
    if not cfg.is_enabled:
        return False
    if cfg.smtp_host:
        return True
    return bool(getattr(settings, "EMAIL_HOST", ""))


def _from_address(cfg: MailTransportConfig) -> str:
    return cfg.default_from_email or getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@delayu.local")


def _smtp_connection(cfg: MailTransportConfig):
    if cfg.smtp_host:
        return get_connection(
            backend="django.core.mail.backends.smtp.EmailBackend",
            host=cfg.smtp_host,
            port=cfg.smtp_port,
            username=cfg.smtp_username or None,
            password=cfg.smtp_password or None,
            use_tls=cfg.smtp_use_tls,
            fail_silently=False,
        )
    return get_connection()


def send_mail_message(
    *,
    subsystem,
    to_addrs: list[str],
    subject: str,
    body: str,
    event_code: str = "",
    html_body: str = "",
) -> tuple[bool, str]:
    """Отправить письмо; возвращает (успех, сообщение об ошибке)."""
    cfg = get_or_create_transport(subsystem)
    if not transport_is_ready(cfg):
        return False, "Почтовый транспорт не настроен"

    recipients = [a.strip() for a in to_addrs if a and a.strip()]
    if not recipients:
        return False, "Нет адресата"

    try:
        msg = EmailMessage(
            subject=subject[:500],
            body=body,
            from_email=_from_address(cfg),
            to=recipients,
            connection=_smtp_connection(cfg),
        )
        if html_body:
            msg.content_subtype = "plain"
            msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=False)
        MailDeliveryLog.objects.create(
            subsystem=subsystem,
            direction=MailDeliveryLog.Direction.OUTBOUND,
            recipient=", ".join(recipients)[:255],
            sender=_from_address(cfg),
            subject=subject[:500],
            event_code=event_code,
            success=True,
        )
        return True, ""
    except Exception as exc:
        logger.warning("mail send failed: %s", exc)
        MailDeliveryLog.objects.create(
            subsystem=subsystem,
            direction=MailDeliveryLog.Direction.OUTBOUND,
            recipient=", ".join(recipients)[:255],
            sender=_from_address(cfg),
            subject=subject[:500],
            event_code=event_code,
            success=False,
            error_message=str(exc)[:2000],
        )
        return False, str(exc)


def _decode_mime(value) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out = []
    for chunk, enc in parts:
        if isinstance(chunk, bytes):
            out.append(chunk.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(chunk)
    return "".join(out)


def _extract_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")[:8000]
        for part in msg.walk():
            if part.get_content_type() == "text/html" and not part.get_filename():
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")[:8000]
    payload = msg.get_payload(decode=True)
    if payload:
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")[:8000]
    return ""


def sync_inbound_mail(subsystem, *, user, limit: int = 30) -> dict:
    """Забрать новые письма по IMAP и зарегистрировать как входящую корреспонденцию."""
    from delayu.services.correspondence import register_correspondence

    cfg = get_or_create_transport(subsystem)
    if not cfg.imap_enabled or not cfg.imap_host:
        return {"ok": False, "error": "IMAP не настроен", "created": 0}

    created = 0
    errors = []
    try:
        if cfg.imap_use_ssl:
            client = imaplib.IMAP4_SSL(cfg.imap_host, cfg.imap_port)
        else:
            client = imaplib.IMAP4(cfg.imap_host, cfg.imap_port)
        client.login(cfg.imap_username, cfg.imap_password)
        client.select(cfg.imap_folder or "INBOX")
        typ, data = client.search(None, "UNSEEN")
        if typ != "OK":
            client.logout()
            return {"ok": False, "error": "Ошибка поиска UNSEEN", "created": 0}
        ids = data[0].split()[-limit:]
        for num in ids:
            typ, fetched = client.fetch(num, "(RFC822)")
            if typ != "OK" or not fetched:
                continue
            raw = fetched[0][1]
            msg = email.message_from_bytes(raw)
            subject = _decode_mime(msg.get("Subject")) or "(без темы)"
            from_hdr = _decode_mime(msg.get("From"))
            _, from_addr = parseaddr(from_hdr)
            body = _extract_body(msg)[:500]
            try:
                corr = register_correspondence(
                    subsystem=subsystem,
                    user=user,
                    direction=Correspondence.Direction.IN,
                    subject=subject[:500],
                    counterparty=from_addr or from_hdr[:255],
                    status=Correspondence.Status.REGISTERED,
                )
                if body:
                    from delayu.services.correspondence import log_event
                    from delayu.models import CorrespondenceEvent

                    log_event(
                        corr,
                        CorrespondenceEvent.EventType.COMMENT,
                        body,
                        actor=user,
                    )
                MailDeliveryLog.objects.create(
                    subsystem=subsystem,
                    direction=MailDeliveryLog.Direction.INBOUND,
                    sender=from_addr[:255],
                    subject=subject[:500],
                    event_code="imap_sync",
                    success=True,
                    correspondence=corr,
                )
                created += 1
                client.store(num, "+FLAGS", "\\Seen")
            except Exception as exc:
                errors.append(str(exc))
                MailDeliveryLog.objects.create(
                    subsystem=subsystem,
                    direction=MailDeliveryLog.Direction.INBOUND,
                    sender=from_addr[:255],
                    subject=subject[:500],
                    event_code="imap_sync",
                    success=False,
                    error_message=str(exc)[:2000],
                )
        client.logout()
        cfg.last_inbound_sync = timezone.now()
        cfg.save(update_fields=["last_inbound_sync", "updated_at"])
    except Exception as exc:
        logger.warning("imap sync failed: %s", exc)
        return {"ok": False, "error": str(exc), "created": created, "errors": errors}

    return {"ok": True, "created": created, "errors": errors}
