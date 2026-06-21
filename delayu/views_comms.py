"""M37–M41 — чат, комментарии, упоминания, ВКС, мессенджеры."""
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, TemplateView

from delayu.forms import ChatMessageForm
from delayu.forms_comms import (
    ChatRoomForm,
    CommentHubForm,
    MessengerChannelForm,
    SubscriptionForm,
    VideoMeetingForm,
)
from delayu.mixins import ModulePermissionMixin
from delayu.models import ChatRoom, Mention, MessengerChannel, ObjectSubscription, VideoMeeting
from delayu.services import audit
from delayu.services.access import user_can
from delayu.services.comms import (
    create_comment,
    filter_chat_rooms,
    filter_comments,
    filter_meetings,
    filter_mentions,
    filter_messenger_channels,
    filter_subscriptions,
    post_chat_message,
)
from delayu.services.workplace import log_activity
from delayu.views_platform import _ctx_membership


class ChatListView(ModulePermissionMixin, TemplateView):
    module_code = "M37"
    template_name = "platform/chat/list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Внутренний чат"
        rooms = list(filter_chat_rooms(m.subsystem, self.request.user, self.request.GET))
        ctx["rooms"] = rooms
        ctx["search_q"] = self.request.GET.get("q", "")
        ctx["comms_tab"] = "chat"
        ctx["can_create"] = user_can(self.request.user, "M37", "create")
        ctx["messages"] = []
        room_pk = self.request.GET.get("room")
        active = None
        if room_pk:
            active = next((r for r in rooms if str(r.pk) == str(room_pk)), None)
        if not active and rooms:
            active = rooms[0]
        if active:
            ctx["active_room"] = active
            ctx["messages"] = active.messages.select_related("author").order_by("created_at")
            ctx["message_form"] = ChatMessageForm()
        profile = getattr(self.request.user, "delayu_profile", None)
        prefs = (profile.theme_prefs if profile else None) or {}
        if prefs.get("avatar_media"):
            from django.conf import settings

            ctx["avatar_url"] = settings.MEDIA_URL + prefs["avatar_media"]
        elif prefs.get("avatar_static"):
            from django.templatetags.static import static

            ctx["avatar_url"] = static(prefs["avatar_static"])
        else:
            from django.templatetags.static import static

            ctx["avatar_url"] = static("img/avatars/1.png")
        return ctx


class ChatCreateView(ModulePermissionMixin, TemplateView):
    module_code = "M37"
    required_action = "create"
    template_name = "platform/chat/create.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Новый чат"
        ctx["form"] = kwargs.get("form") or ChatRoomForm(subsystem=m.subsystem)
        ctx["comms_tab"] = "chat"
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = ChatRoomForm(request.POST, subsystem=m.subsystem)
        if form.is_valid():
            room = form.save(commit=False)
            room.subsystem = m.subsystem
            room.save()
            form.save_m2m()
            room.members.add(request.user)
            messages.success(request, "Чат создан.")
            return redirect(f"{reverse('platform-chat')}?room={room.pk}")
        return self.render_to_response(self.get_context_data(form=form))


class ChatDetailView(ModulePermissionMixin, DetailView):
    """Старый URL чата — перенаправление на единую страницу списка."""

    module_code = "M37"
    model = ChatRoom

    def get(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        room = get_object_or_404(
            ChatRoom, pk=kwargs["pk"], subsystem=m.subsystem, members=request.user
        )
        return redirect(f"{reverse('platform-chat')}?room={room.pk}")


class ChatDeleteView(ModulePermissionMixin, View):
    module_code = "M37"
    required_action = "delete"

    def post(self, request, pk):
        m = _ctx_membership(self)
        room = get_object_or_404(
            ChatRoom, pk=pk, subsystem=m.subsystem, members=request.user
        )
        name = room.name
        room.delete()
        messages.success(request, f"Чат «{name}» удалён.")
        return redirect("platform-chat")


class ChatPostView(ModulePermissionMixin, View):
    module_code = "M37"
    required_action = "create"

    def post(self, request, pk):
        m = _ctx_membership(self)
        room = get_object_or_404(
            ChatRoom, pk=pk, subsystem=m.subsystem, members=request.user
        )
        form = ChatMessageForm(request.POST)
        if form.is_valid():
            post_chat_message(room=room, author=request.user, body=form.cleaned_data["body"])
            log_activity(
                m.subsystem,
                request.user,
                "messaged",
                room.name,
                module_code="M37",
                link_path=f"/chat/{room.pk}/",
            )
        return redirect(f"{reverse('platform-chat')}?room={pk}")


class CommentsHubView(ModulePermissionMixin, TemplateView):
    module_code = "M38"
    template_name = "platform/comms/comments.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Комментарии"
        from django.db.models import Prefetch
        from delayu.models import Comment

        qs = filter_comments(m.subsystem, self.request.GET).prefetch_related(
            Prefetch("replies", queryset=Comment.objects.select_related("author"))
        )[:100]
        ctx["comments"] = qs
        ctx["form"] = CommentHubForm(subsystem=m.subsystem)
        ctx["comms_tab"] = "comments"
        ctx["filter_module"] = self.request.GET.get("module", "")
        ctx["can_create"] = user_can(self.request.user, "M38", "create")
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        if not user_can(request.user, "M38", "create"):
            messages.error(request, "Нет прав.")
            return redirect("platform-comments")
        form = CommentHubForm(request.POST, subsystem=m.subsystem)
        if form.is_valid():
            case = form.cleaned_data.get("case")
            create_comment(
                subsystem=m.subsystem,
                author=request.user,
                body=form.cleaned_data["body"],
                case=case,
            )
            messages.success(request, "Комментарий добавлен.")
        return redirect("platform-comments")


class CaseCommentView(ModulePermissionMixin, View):
    module_code = "M38"
    required_action = "create"

    def post(self, request, pk):
        from delayu.models import CaseFile

        case = get_object_or_404(CaseFile, pk=pk)
        body = request.POST.get("body", "").strip()
        parent_id = request.POST.get("parent_id")
        if body and not case.is_archived:
            parent = None
            if parent_id:
                from delayu.models import Comment

                parent = Comment.objects.filter(pk=parent_id, case=case).first()
            create_comment(
                subsystem=case.subsystem,
                author=request.user,
                body=body,
                case=case,
                parent=parent,
            )
        return redirect("platform-case-detail", pk=pk)


class MentionsListView(ModulePermissionMixin, TemplateView):
    module_code = "M39"
    template_name = "platform/comms/mentions.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        unread = self.request.GET.get("unread") == "1"
        ctx["page_title"] = "Упоминания"
        ctx["mentions"] = filter_mentions(
            self.request.user, m.subsystem, unread_only=unread
        )
        ctx["unread_only"] = unread
        ctx["comms_tab"] = "mentions"
        ctx["unread_count"] = filter_mentions(
            self.request.user, m.subsystem, unread_only=True
        ).count()
        return ctx


class MentionReadView(ModulePermissionMixin, View):
    module_code = "M39"
    required_action = "change"

    def post(self, request, pk):
        m = _ctx_membership(self)
        mention = get_object_or_404(
            Mention, pk=pk, mentioned_user=request.user, subsystem=m.subsystem
        )
        mention.is_read = True
        mention.save(update_fields=["is_read"])
        if mention.link_path:
            return redirect(mention.link_path)
        return redirect("platform-mentions")


class SubscriptionsListView(ModulePermissionMixin, TemplateView):
    module_code = "M39"
    template_name = "platform/comms/subscriptions.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Подписки на объекты"
        ctx["subscriptions"] = filter_subscriptions(self.request.user, m.subsystem)
        ctx["form"] = SubscriptionForm(subsystem=m.subsystem)
        ctx["comms_tab"] = "subscriptions"
        ctx["can_create"] = user_can(self.request.user, "M39", "create")
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = SubscriptionForm(request.POST, subsystem=m.subsystem)
        if form.is_valid():
            ttype = form.cleaned_data["target_type"]
            case = form.cleaned_data.get("case")
            document = form.cleaned_data.get("document")
            if ttype == ObjectSubscription.TargetType.CASE and case:
                ObjectSubscription.objects.get_or_create(
                    user=request.user,
                    subsystem=m.subsystem,
                    target_type=ttype,
                    case=case,
                )
                messages.success(request, f"Подписка на дело {case.number}.")
            elif ttype == ObjectSubscription.TargetType.DOCUMENT and document:
                ObjectSubscription.objects.get_or_create(
                    user=request.user,
                    subsystem=m.subsystem,
                    target_type=ttype,
                    document=document,
                )
                messages.success(request, "Подписка на документ оформлена.")
            else:
                messages.error(request, "Выберите объект для подписки.")
        return redirect("platform-subscriptions")


class SubscriptionDeleteView(ModulePermissionMixin, View):
    module_code = "M39"
    required_action = "delete"

    def post(self, request, pk):
        m = _ctx_membership(self)
        sub = get_object_or_404(
            ObjectSubscription, pk=pk, user=request.user, subsystem=m.subsystem
        )
        sub.delete()
        messages.success(request, "Подписка удалена.")
        return redirect("platform-subscriptions")


class MeetingsListView(ModulePermissionMixin, TemplateView):
    module_code = "M40"
    template_name = "platform/comms/meetings.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Видеосовещания"
        ctx["meetings"] = filter_meetings(m.subsystem, self.request.GET)
        ctx["upcoming_only"] = self.request.GET.get("upcoming") == "1"
        ctx["comms_tab"] = "meetings"
        ctx["can_create"] = user_can(self.request.user, "M40", "create")
        return ctx


class MeetingCreateView(ModulePermissionMixin, TemplateView):
    module_code = "M40"
    required_action = "create"
    template_name = "platform/comms/meeting_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Новое совещание"
        ctx["form"] = kwargs.get("form") or VideoMeetingForm(subsystem=m.subsystem)
        ctx["comms_tab"] = "meetings"
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = VideoMeetingForm(request.POST, subsystem=m.subsystem)
        if form.is_valid():
            meeting = form.save(commit=False)
            meeting.subsystem = m.subsystem
            meeting.created_by = request.user
            meeting.save()
            messages.success(request, "Совещение запланировано.")
            return redirect("platform-meetings")
        return self.render_to_response(self.get_context_data(form=form))


class MessengersListView(ModulePermissionMixin, TemplateView):
    module_code = "M41"
    template_name = "platform/comms/messengers.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Мессенджеры"
        ctx["channels"] = filter_messenger_channels(m.subsystem)
        ctx["comms_tab"] = "messengers"
        ctx["can_create"] = user_can(self.request.user, "M41", "create")
        return ctx


class MessengerCreateView(ModulePermissionMixin, TemplateView):
    module_code = "M41"
    required_action = "create"
    template_name = "platform/comms/messenger_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Канал мессенджера"
        ctx["form"] = kwargs.get("form") or MessengerChannelForm()
        ctx["comms_tab"] = "messengers"
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = MessengerChannelForm(request.POST)
        if form.is_valid():
            ch = form.save(commit=False)
            ch.subsystem = m.subsystem
            ch.save()
            audit.log_action(
                request.user, m.subsystem, "messenger.create", "MessengerChannel", ch.pk, request=request
            )
            messages.success(request, "Канал сохранён.")
            return redirect("platform-messengers")
        return self.render_to_response(self.get_context_data(form=form))
