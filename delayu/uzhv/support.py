"""Чат обратной связи УЖВ: Odysseus и специалист техподдержки."""
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import TemplateView

from delayu.menu import get_active_membership
from delayu.mixins import MethodActionPermissionMixin
from delayu.models_uzhv import UzhvSupportMessage, UzhvSupportThread
from delayu.services.access import get_membership_or_403, user_can
from delayu.services.uzhv_roles import SUPPORT_STAFF_ROLES
from delayu.services.uzhv_support_chat import ask_odysseus


class UzhvSupportChatView(MethodActionPermissionMixin, TemplateView):
    module_code = "U04"
    template_name = "platform/uzhv/support_chat.html"
    page_title = "Поддержка"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            mem = get_membership_or_403(request)
            if mem.subsystem.industry_template != "uzhv":
                raise PermissionDenied("Раздел доступен только в контуре АИС УЖВ")
        return super().dispatch(request, *args, **kwargs)

    def get_subsystem(self):
        return get_membership_or_403(self.request).subsystem

    def _is_staff(self) -> bool:
        membership = get_active_membership(self.request.user)
        code = getattr(getattr(membership, "role", None), "code", "") or ""
        if code in SUPPORT_STAFF_ROLES:
            return True
        return user_can(self.request.user, "U04", "change")

    def _threads(self):
        subsystem = self.get_subsystem()
        qs = UzhvSupportThread.objects.filter(subsystem=subsystem)
        if not self._is_staff():
            qs = qs.filter(author=self.request.user)
        return qs

    def _thread(self):
        pk = self.kwargs.get("pk")
        if not pk:
            return None
        return get_object_or_404(self._threads(), pk=pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        thread = self._thread()
        ctx["page_title"] = "Поддержка"
        ctx["threads"] = self._threads()[:40]
        ctx["thread"] = thread
        ctx["chat_messages"] = thread.messages.all() if thread else []
        ctx["is_support_staff"] = self._is_staff()
        ctx["can_create"] = user_can(self.request.user, "U04", "create")
        return ctx

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "message").strip()
        thread = self._thread()
        if action == "new" or thread is None:
            return self._start(request)
        if action == "escalate":
            return self._escalate(request, thread)
        if action == "specialist":
            return self._specialist(request, thread)
        if action == "close":
            thread.status = UzhvSupportThread.Status.CLOSED
            thread.save(update_fields=["status", "updated_at"])
            self._system(thread, "Обращение закрыто.")
            return redirect("uzhv-support-thread", pk=thread.pk)
        return self._user_message(request, thread)

    def _start(self, request):
        body = (request.POST.get("body") or "").strip()
        if not body:
            messages.error(request, "Напишите вопрос.")
            return redirect("uzhv-support")
        subject = (request.POST.get("subject") or body).strip().splitlines()[0][:200]
        thread = UzhvSupportThread.objects.create(
            subsystem=self.get_subsystem(),
            author=request.user,
            subject=subject,
        )
        return self._user_message(request, thread, body=body)

    def _user_message(self, request, thread, body=None):
        if thread.status == UzhvSupportThread.Status.CLOSED:
            messages.error(request, "Обращение закрыто. Начните новое.")
            return redirect("uzhv-support-thread", pk=thread.pk)
        text = (body if body is not None else request.POST.get("body") or "").strip()
        if not text:
            messages.error(request, "Пустое сообщение.")
            return redirect("uzhv-support-thread", pk=thread.pk)
        if thread.author_id != request.user.id and not self._is_staff():
            messages.error(request, "Это чужое обращение.")
            return redirect("uzhv-support")
        UzhvSupportMessage.objects.create(
            thread=thread,
            author=request.user,
            role=UzhvSupportMessage.Role.USER,
            body=text[:4000],
        )
        history = [
            {"role": item.role, "content": item.body}
            for item in thread.messages.all()
        ]
        answer, engine = ask_odysseus(subsystem=thread.subsystem, history=history)
        UzhvSupportMessage.objects.create(
            thread=thread,
            role=UzhvSupportMessage.Role.ASSISTANT,
            body=answer[:8000],
            engine=engine[:64],
        )
        if thread.status == UzhvSupportThread.Status.ANSWERED:
            thread.status = UzhvSupportThread.Status.OPEN
        thread.updated_at = timezone.now()
        thread.save(update_fields=["status", "updated_at"])
        return redirect("uzhv-support-thread", pk=thread.pk)

    def _escalate(self, request, thread):
        thread.status = UzhvSupportThread.Status.ESCALATED
        thread.save(update_fields=["status", "updated_at"])
        self._system(
            thread,
            "Обращение передано специалисту технической поддержки. Ответ появится в этом чате.",
        )
        messages.success(request, "Обращение передано специалисту ТП.")
        return redirect("uzhv-support-thread", pk=thread.pk)

    def _specialist(self, request, thread):
        if not self._is_staff():
            messages.error(request, "Отвечать от имени ТП может руководитель или администратор контура.")
            return redirect("uzhv-support-thread", pk=thread.pk)
        text = (request.POST.get("body") or "").strip()
        if not text:
            messages.error(request, "Напишите ответ.")
            return redirect("uzhv-support-thread", pk=thread.pk)
        UzhvSupportMessage.objects.create(
            thread=thread,
            author=request.user,
            role=UzhvSupportMessage.Role.SPECIALIST,
            body=text[:4000],
        )
        thread.status = UzhvSupportThread.Status.ANSWERED
        thread.save(update_fields=["status", "updated_at"])
        return redirect("uzhv-support-thread", pk=thread.pk)

    def _system(self, thread, text: str):
        UzhvSupportMessage.objects.create(
            thread=thread,
            role=UzhvSupportMessage.Role.SYSTEM,
            body=text,
        )
