"""Диспетчер уведомлений: in-app + e-mail по шаблонам M78."""
from __future__ import annotations

from django.contrib.auth import get_user_model

from delayu.models import Notification, NotificationTemplate
from delayu.services.mail import send_mail_message

User = get_user_model()


def _format_template(text: str, context: dict) -> str:
    out = text or ""
    for key, val in context.items():
        out = out.replace("{" + key + "}", str(val))
        out = out.replace("{{" + key + "}}", str(val))
    return out


def _recipients(users) -> list[User]:
    seen = set()
    out = []
    for u in users:
        if not u or u.pk in seen:
            continue
        seen.add(u.pk)
        out.append(u)
    return out


def _user_sms_phone(user) -> str:
    profile = getattr(user, "delayu_profile", None)
    if not profile:
        return ""
    return (profile.phone_mobile or profile.phone or "").strip()


def _user_telegram(user) -> str:
    profile = getattr(user, "delayu_profile", None)
    if not profile:
        return ""
    chat_id = (getattr(profile, "telegram_chat_id", "") or "").strip()
    if chat_id:
        return chat_id
    return (profile.telegram or "").strip()


def _log_mobile_alert(subsystem, *, recipient: str, subject: str, body: str, event_code: str):
    from delayu.models import MailDeliveryLog

    text = f"{subject}\n{body}"[:500]
    MailDeliveryLog.objects.create(
        subsystem=subsystem,
        direction=MailDeliveryLog.Direction.OUTBOUND,
        recipient=recipient[:255],
        subject=subject[:500],
        event_code=event_code,
        success=True,
        error_message=text[:2000],
    )


def _send_sms_template(user, subsystem, *, subject: str, body: str, event_code: str):
    """SMS/Telegram M78: Telegram Bot API при настроенном M41, иначе журнал."""
    telegram = _user_telegram(user)
    if telegram:
        from delayu.services.telegram import send_telegram_message

        text = f"{subject}\n{body}"[:4096]
        if send_telegram_message(
            subsystem, telegram, text, event_code=f"{event_code}_telegram"
        ):
            return
        _log_mobile_alert(
            subsystem,
            recipient=f"telegram:{telegram}",
            subject=subject,
            body=body,
            event_code=f"{event_code}_telegram",
        )
        return
    phone = _user_sms_phone(user)
    if not phone:
        return
    from delayu.services.max_messenger import send_max_message

    if send_max_message(subsystem, phone, f"{subject}\n{body}", event_code=f"{event_code}_max"):
        return
    _log_mobile_alert(
        subsystem,
        recipient=phone,
        subject=subject,
        body=body,
        event_code=event_code or "sms",
    )


def dispatch_event(subsystem, event_code: str, users, context: dict | None = None):
    """
    Отправить уведомление по шаблонам подсистемы (in_app и email).
    context: user, case, link, reg_number, subject, step_name, comment, ...
    """
    context = dict(context or {})
    for user in _recipients(users):
        if not user:
            continue
        ctx = {**context, "user": user.get_full_name() or user.username}
        templates = NotificationTemplate.objects.filter(
            subsystem=subsystem,
            event_code=event_code,
            is_active=True,
        )
        for tpl in templates:
            body = _format_template(tpl.body, ctx)
            subject = _format_template(tpl.subject or event_code, ctx)
            if tpl.channel == NotificationTemplate.Channel.IN_APP:
                Notification.objects.create(
                    user=user,
                    subsystem=subsystem,
                    title=subject[:255],
                    body=body[:2000],
                    link=context.get("link", "")[:500],
                    level=Notification.Level.INFO,
                )
            elif tpl.channel == NotificationTemplate.Channel.EMAIL and user.email:
                send_mail_message(
                    subsystem=subsystem,
                    to_addrs=[user.email],
                    subject=subject,
                    body=body,
                    event_code=event_code,
                )
            elif tpl.channel == NotificationTemplate.Channel.SMS:
                _send_sms_template(user, subsystem, subject=subject, body=body, event_code=event_code)


def notify_bpm_task_assigned(task):
    assignee = task.assignee
    if not assignee:
        return
    case = task.instance.case
    subsystem = task.instance.template.subsystem
    dispatch_event(
        subsystem,
        "bpm_step_assigned",
        [assignee],
        {
            "case": f"{case.number} — {case.title}" if case else "—",
            "step_name": task.step_name,
            "link": f"/bpm/approvals/",
        },
    )


def notify_bpm_task_escalated(task, *, from_user, role_code: str):
    assignee = task.assignee
    if not assignee:
        return
    case = task.instance.case
    subsystem = task.instance.template.subsystem
    dispatch_event(
        subsystem,
        "bpm_step_escalated",
        [assignee],
        {
            "case": f"{case.number} — {case.title}" if case else "—",
            "step_name": task.step_name,
            "from_user": from_user.get_full_name() or from_user.username,
            "role": role_code,
            "link": "/bpm/approvals/",
        },
    )


def notify_bpm_finished(instance, *, approved: bool):
    subsystem = instance.template.subsystem
    case = instance.case
    users = []
    if case and case.assignee:
        users.append(case.assignee)
    code = "bpm_completed" if approved and instance.status == instance.Status.COMPLETED else "bpm_rejected"
    if not users:
        return
    dispatch_event(
        subsystem,
        code,
        users,
        {
            "case": f"{case.number} — {case.title}" if case else "—",
            "link": f"/cases/{case.pk}/" if case else "/bpm/",
        },
    )


def notify_correspondence_routed(correspondence, from_user, to_user, comment=""):
    dispatch_event(
        correspondence.subsystem,
        "corr_routed",
        [to_user],
        {
            "reg_number": correspondence.reg_number,
            "subject": correspondence.subject,
            "user": from_user.get_full_name() or from_user.username,
            "comment": comment[:200],
            "link": f"/correspondence/{correspondence.pk}/",
        },
    )


def notify_correspondence_workflow_done(correspondence, actor):
    """Уведомление по завершению маршрута СЭД (последний шаг workflow)."""
    wf = correspondence.subsystem.correspondence_workflow or {}
    steps = wf.get("steps") or []
    if steps and steps[-1] != "archive":
        return
    recipients = []
    if correspondence.assignee:
        recipients.append(correspondence.assignee)
    if correspondence.created_by_id and correspondence.created_by not in recipients:
        recipients.append(correspondence.created_by)
    dispatch_event(
        correspondence.subsystem,
        "corr_workflow_complete",
        recipients,
        {
            "reg_number": correspondence.reg_number,
            "subject": correspondence.subject,
            "user": actor.get_full_name() or actor.username,
            "link": f"/correspondence/{correspondence.pk}/",
        },
    )


def notify_uzhv_deadline_urgent(subsystem, user, *, title: str, body: str, link: str) -> bool:
    """E-mail по шаблону uzhv_deadline_urgent (in-app создаёт sync_uzhv_deadline_notifications)."""
    dispatch_event(
        subsystem,
        "uzhv_deadline_urgent",
        [user],
        {"title": title, "body": body, "link": link, "subject": title},
    )
    from delayu.services.uzhv_webpush import send_uzhv_web_push

    return send_uzhv_web_push(user, title=title, body=body, url=link)


def notify_correspondence_closed(correspondence, actor):
    correspondence.status = correspondence.Status.CLOSED
    correspondence.save(update_fields=["status"])
    recipients = []
    if correspondence.assignee:
        recipients.append(correspondence.assignee)
    if correspondence.created_by_id and correspondence.created_by not in recipients:
        recipients.append(correspondence.created_by)
    dispatch_event(
        correspondence.subsystem,
        "corr_workflow_complete",
        recipients,
        {
            "reg_number": correspondence.reg_number,
            "subject": correspondence.subject,
            "user": actor.get_full_name() or actor.username,
            "link": f"/correspondence/{correspondence.pk}/",
        },
    )
