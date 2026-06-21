"""M37–M41 — чат, комментарии, упоминания, ВКС, мессенджеры."""
import re

from django.contrib.auth import get_user_model
from django.db.models import Q

from delayu.models import (
    ChatMessage,
    ChatRoom,
    Comment,
    DocumentFile,
    Mention,
    MessengerChannel,
    Notification,
    ObjectSubscription,
    VideoMeeting,
)

User = get_user_model()
MENTION_RE = re.compile(r"@([A-Za-z0-9_]+)")


def filter_chat_rooms(subsystem, user, params=None):
    params = params or {}
    qs = ChatRoom.objects.filter(subsystem=subsystem, members=user).select_related("case")
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(case__number__icontains=q))
    return qs.order_by("-created_at")


def filter_comments(subsystem, params=None):
    params = params or {}
    qs = Comment.objects.filter(subsystem=subsystem, parent__isnull=True).select_related(
        "author", "case", "document"
    )
    if params.get("case"):
        qs = qs.filter(case_id=params["case"])
    if params.get("module") == "document":
        qs = qs.filter(document__isnull=False)
    elif params.get("module") == "case":
        qs = qs.filter(case__isnull=False, document__isnull=True)
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(body__icontains=q)
    return qs.order_by("-created_at")


def process_mentions(*, subsystem, author, body, link_path, comment=None, chat_message=None):
    for username in MENTION_RE.findall(body):
        user = User.objects.filter(username=username).first()
        if not user or user.pk == author.pk:
            continue
        Mention.objects.create(
            subsystem=subsystem,
            mentioned_user=user,
            author=author,
            comment=comment,
            chat_message=chat_message,
            excerpt=body[:200],
            link_path=link_path,
        )
        Notification.objects.create(
            user=user,
            subsystem=subsystem,
            title=f"Упоминание от {author.get_full_name() or author.username}",
            body=body[:255],
            link=link_path,
            level=Notification.Level.INFO,
        )


def create_comment(*, subsystem, author, body, case=None, document=None, parent=None):
    comment = Comment.objects.create(
        subsystem=subsystem,
        case=case,
        document=document,
        parent=parent,
        author=author,
        body=body,
    )
    link = f"/cases/{case.pk}/" if case else "/comms/comments/"
    process_mentions(
        subsystem=subsystem,
        author=author,
        body=body,
        link_path=link,
        comment=comment,
    )
    if case:
        for sub in ObjectSubscription.objects.filter(
            subsystem=subsystem, target_type=ObjectSubscription.TargetType.CASE, case=case
        ).exclude(user=author):
            Notification.objects.create(
                user=sub.user,
                subsystem=subsystem,
                title=f"Комментарий к делу {case.number}",
                body=body[:255],
                link=link,
            )
    return comment


def post_chat_message(*, room, author, body):
    msg = ChatMessage.objects.create(room=room, author=author, body=body)
    process_mentions(
        subsystem=room.subsystem,
        author=author,
        body=body,
        link_path=f"/chat/{room.pk}/",
        chat_message=msg,
    )
    return msg


def filter_mentions(user, subsystem, *, unread_only=False):
    qs = Mention.objects.filter(mentioned_user=user, subsystem=subsystem).select_related(
        "author", "comment", "chat_message"
    )
    if unread_only:
        qs = qs.filter(is_read=False)
    return qs[:80]


def filter_subscriptions(user, subsystem):
    return ObjectSubscription.objects.filter(user=user, subsystem=subsystem).select_related(
        "case", "document"
    )


def filter_meetings(subsystem, params=None):
    params = params or {}
    qs = VideoMeeting.objects.filter(subsystem=subsystem).select_related("case", "created_by")
    if params.get("upcoming") == "1":
        from django.utils import timezone

        qs = qs.filter(scheduled_at__gte=timezone.now())
    return qs.order_by("scheduled_at")


def filter_messenger_channels(subsystem):
    return MessengerChannel.objects.filter(subsystem=subsystem).order_by("code")
