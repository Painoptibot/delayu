"""M07–M14 — рабочее место: кабинет, задачи, календарь, канбан, Гант, уведомления, избранное, лента."""
import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from delayu.forms import TaskItemForm
from delayu.forms_workplace import CabinetPrefsForm, CabinetProfileForm, FavoriteForm, SavedFilterForm
from delayu.mixins import ModulePermissionMixin
from delayu.models import (
    ActivityEvent,
    BPMTask,
    Favorite,
    Notification,
    SavedFilter,
    SubsystemMembership,
    TaskItem,
    UserProfile,
)
from delayu.models_business import Correspondence, PROFILE_ATTRIBUTE_GROUPS
from delayu.services import studio
from delayu.services.access import user_can
from delayu.services.workplace import cabinet_stats, gantt_rows, log_activity, today_inbox_preview
from delayu.views_platform import _ctx_membership

User = get_user_model()


class CabinetView(ModulePermissionMixin, TemplateView):
    """Базовый контекст личного кабинета."""

    module_code = "M07"
    template_name = "platform/workplace/cabinet_account.html"
    cabinet_tab = "account"

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        if not user_can(request.user, "M07", "change"):
            messages.error(request, "Нет прав на изменение профиля.")
            return redirect("platform-cabinet")
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        preset = request.POST.get("avatar_preset")
        upload = request.FILES.get("avatar")
        if preset and preset.startswith("img/avatars/"):
            prefs = dict(profile.theme_prefs or {})
            prefs["avatar_static"] = preset
            prefs.pop("avatar_media", None)
            profile.theme_prefs = prefs
            profile.save(update_fields=["theme_prefs", "updated_at"])
            messages.success(request, "Аватар обновлён.")
        elif upload:
            from django.core.files.storage import default_storage

            ext = upload.name.rsplit(".", 1)[-1].lower()[:8]
            if ext not in ("png", "jpg", "jpeg", "webp", "gif"):
                messages.error(request, "Допустимы изображения PNG, JPG или WebP.")
            else:
                path = default_storage.save(
                    f"avatars/user_{request.user.pk}.{ext}", upload
                )
                prefs = dict(profile.theme_prefs or {})
                prefs["avatar_media"] = path
                prefs.pop("avatar_static", None)
                profile.theme_prefs = prefs
                profile.save(update_fields=["theme_prefs", "updated_at"])
                messages.success(request, "Фото профиля загружено.")
        form = CabinetProfileForm(request.POST)
        if form.is_valid():
            form.save(request.user)
            log_activity(
                m.subsystem,
                request.user,
                "обновил профиль в личном кабинете",
                request.user,
                module_code="M07",
            )
            messages.success(request, "Данные профиля сохранены.")
        else:
            messages.error(request, "Проверьте поля формы.")
        return redirect("platform-cabinet")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        u = self.request.user
        ctx["page_title"] = "Личный кабинет"
        ctx["stats"] = cabinet_stats(u, m.subsystem)
        ctx["tasks_open"] = TaskItem.objects.filter(
            subsystem=m.subsystem, assignee=u, completed_at__isnull=True
        ).order_by("-priority", "due_date")[:8]
        ctx["bpm_pending"] = BPMTask.objects.filter(
            assignee=u, status=BPMTask.Status.PENDING
        ).select_related("instance__case")[:5]
        ctx["notifications"] = Notification.objects.filter(
            user=u, subsystem=m.subsystem, is_read=False
        )[:8]
        ctx["favorites"] = Favorite.objects.filter(user=u).filter(
            Q(subsystem=m.subsystem) | Q(subsystem__isnull=True)
        )[:12]
        profile, _ = UserProfile.objects.get_or_create(user=u)
        ctx["profile"] = profile
        prefs = profile.theme_prefs or {}
        if prefs.get("avatar_media"):
            from django.conf import settings

            ctx["avatar_url"] = settings.MEDIA_URL + prefs["avatar_media"]
        elif prefs.get("avatar_static"):
            from django.templatetags.static import static

            ctx["avatar_url"] = static(prefs["avatar_static"])
        else:
            from django.templatetags.static import static

            ctx["avatar_url"] = static("img/avatars/1.png")
        ctx["avatar_presets"] = [f"img/avatars/{i}.png" for i in range(1, 9)]
        ctx["avatar_preset_active"] = prefs.get("avatar_static", "img/avatars/1.png")
        ctx["profile_form"] = CabinetProfileForm(
            initial=CabinetProfileForm.initial_from_user(u, profile),
            subsystem=m.subsystem,
        )
        ctx["memberships"] = SubsystemMembership.objects.filter(user=u).select_related(
            "subsystem", "role", "organization"
        )
        mem = m
        ctx["active_membership"] = mem
        ctx["active_role"] = mem.role.name if mem else ""
        ctx["active_org"] = mem.organization.name if mem and mem.organization else ""
        ctx["can_change"] = user_can(u, "M07", "change")
        ctx["cabinet_tab"] = self.cabinet_tab
        ctx["cabinet_layout_json"] = json.dumps(
            studio.cabinet_widgets_for_profile(profile), ensure_ascii=False
        )
        ctx["inbox_preview"] = Correspondence.objects.filter(
            subsystem=m.subsystem,
            assignee=u,
            is_deleted=False,
        ).order_by("-reg_date")[:6]
        ctx["profile_field_groups"] = self._profile_field_groups(
            ctx["profile_form"], u, profile
        )
        return ctx

    def _profile_field_groups(self, form, user, profile):
        readonly = {
            "username": user.username,
            "is_active": "Да" if user.is_active else "Нет",
            "last_login": (
                timezone.localtime(user.last_login).strftime("%d.%m.%Y %H:%M")
                if user.last_login
                else "—"
            ),
            "must_change_password": "Да" if profile.must_change_password else "Нет",
            "two_factor_enabled": "Да" if profile.two_factor_enabled else "Нет",
        }
        groups = []
        for group in PROFILE_ATTRIBUTE_GROUPS:
            items = []
            for fname, label in group["fields"]:
                if fname in readonly:
                    items.append(
                        {"label": label, "value": readonly[fname], "readonly": True}
                    )
                elif fname in form.fields:
                    items.append({"field": form[fname]})
            if items:
                groups.append({"title": group["title"], "items": items})
        return groups


class CabinetAccountView(CabinetView):
    template_name = "platform/workplace/cabinet_account.html"
    cabinet_tab = "account"


class CabinetSecurityView(CabinetView):
    template_name = "platform/workplace/cabinet_security.html"
    cabinet_tab = "security"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from delayu.services.session_registry import list_user_sessions

        ctx["sessions"] = list_user_sessions(
            self.request.user, current_key=self.request.session.session_key or ""
        )
        return ctx


class CabinetSessionRevokeView(CabinetView):
    def post(self, request, *args, **kwargs):
        from delayu.services.session_registry import revoke_session

        key = request.POST.get("session_key", "")
        if revoke_session(request.user, key, current_key=request.session.session_key or ""):
            messages.success(request, "Сессия завершена.")
        else:
            messages.error(request, "Не удалось завершить сессию.")
        return redirect("platform-cabinet-security")


class CabinetDelegationCreateView(CabinetView):
    def post(self, request, *args, **kwargs):
        from django.contrib.auth import get_user_model

        from delayu.services.delegation import create_delegation

        m = _ctx_membership(self)
        User = get_user_model()
        to_id = request.POST.get("to_user")
        start = request.POST.get("start_at")
        end = request.POST.get("end_at")
        try:
            to_user = User.objects.get(pk=to_id)
            from datetime import datetime

            start_at = datetime.strptime(start, "%Y-%m-%d").date()
            end_at = datetime.strptime(end, "%Y-%m-%d").date()
            create_delegation(
                subsystem=m.subsystem,
                from_user=request.user,
                to_user=to_user,
                start_at=start_at,
                end_at=end_at,
            )
            messages.success(request, f"Полномочия делегированы пользователю {to_user.username}.")
        except Exception as exc:
            messages.error(request, str(exc))
        return redirect("platform-cabinet-notifications")


class CabinetDelegationRevokeView(CabinetView):
    def post(self, request, *args, **kwargs):
        from delayu.models import Delegation
        from delayu.services.delegation import revoke_delegation

        m = _ctx_membership(self)
        deleg = get_object_or_404(
            Delegation, pk=request.POST.get("delegation_id"), subsystem=m.subsystem, from_user=request.user
        )
        revoke_delegation(deleg)
        messages.success(request, "Делегирование отозвано.")
        return redirect("platform-cabinet-notifications")


class CabinetBillingView(CabinetView):
    template_name = "platform/workplace/cabinet_billing.html"
    cabinet_tab = "billing"


class CabinetAccessView(CabinetView):
    template_name = "platform/workplace/cabinet_access.html"
    cabinet_tab = "access"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from delayu.models import ModuleCatalog, RoleModulePermission, SubsystemModule

        m = _ctx_membership(self)
        perms = []
        if m:
            enabled = SubsystemModule.objects.filter(
                subsystem=m.subsystem, enabled=True
            ).select_related("module")
            for link in enabled:
                mod = link.module
                rp = RoleModulePermission.objects.filter(role=m.role, module=mod).first()
                perms.append(
                    {
                        "code": mod.code,
                        "name": mod.name,
                        "view": bool(rp and rp.can_view),
                        "create": bool(rp and rp.can_create),
                        "change": bool(rp and rp.can_change),
                        "delete": bool(rp and rp.can_delete),
                    }
                )
        ctx["module_permissions"] = perms
        if m:
            from delayu.services.delegation import active_delegations_qs

            ctx["delegations_given"] = active_delegations_qs(
                subsystem=m.subsystem, user=self.request.user, direction="given"
            )
            ctx["delegations_received"] = active_delegations_qs(
                subsystem=m.subsystem, user=self.request.user, direction="received"
            )
            ctx["delegation_candidates"] = User.objects.filter(
                subsystem_memberships__subsystem=m.subsystem
            ).exclude(pk=self.request.user.pk).distinct().order_by("username")
        return ctx


class CabinetConnectionsView(CabinetView):
    template_name = "platform/workplace/cabinet_connections.html"
    cabinet_tab = "connections"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from django.conf import settings

        from delayu.services.uzhv_pwa import push_subscription_status, user_has_uzhv_membership

        u = self.request.user
        ctx["uzhv_user"] = user_has_uzhv_membership(u)
        if ctx["uzhv_user"]:
            ctx["uzhv_push_status"] = push_subscription_status(u)
            ctx["uzhv_vapid_public_key"] = getattr(settings, "UZHV_VAPID_PUBLIC_KEY", "")
            ctx["uzhv_push_subscribe_url"] = reverse("platform-cabinet-uzhv-push")
            ctx["uzhv_sw_url"] = reverse("uzhv-service-worker")
        return ctx


class CabinetUzhvPushView(ModulePermissionMixin, View):
    """Web Push subscribe/unsubscribe из личного кабинета (без активного контура УЖВ)."""

    module_code = "M07"

    def dispatch(self, request, *args, **kwargs):
        from delayu.services.uzhv_pwa import user_has_uzhv_membership

        if not user_has_uzhv_membership(request.user):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("Нет доступа к контуру АИС УЖВ")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        import json

        from delayu.services.uzhv_pwa import save_push_subscription

        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "invalid json"}, status=400)
        ok = save_push_subscription(request.user, payload)
        return JsonResponse({"ok": ok})

    def delete(self, request):
        from delayu.services.uzhv_pwa import clear_push_subscription

        clear_push_subscription(request.user)
        return JsonResponse({"ok": True})


class CabinetUzhvPushTestView(ModulePermissionMixin, View):
    module_code = "M07"

    def post(self, request):
        from delayu.services.uzhv_pwa import user_has_uzhv_membership
        from delayu.services.uzhv_webpush import send_uzhv_web_push

        if not user_has_uzhv_membership(request.user):
            return JsonResponse({"ok": False, "error": "no uzhv"}, status=403)
        ok = send_uzhv_web_push(
            request.user,
            title="АИС УЖВ: тест",
            body="Push-канал работает.",
            url="/uzhv/",
        )
        return JsonResponse({"ok": ok, "push": ok})


class CabinetPrefsView(ModulePermissionMixin, View):
    """Совместимость со старым URL — перенаправление в кабинет."""

    module_code = "M07"

    def post(self, request):
        return redirect("platform-cabinet")


class TodayView(ModulePermissionMixin, ListView):
    module_code = "M08"
    template_name = "platform/workplace/today.html"
    context_object_name = "tasks"
    paginate_by = 50

    def get_queryset(self):
        m = _ctx_membership(self)
        today = timezone.now().date()
        qs = TaskItem.objects.filter(
            subsystem=m.subsystem,
            assignee=self.request.user,
            completed_at__isnull=True,
        ).select_related("case")
        tab = self.request.GET.get("tab", "today")
        if tab == "overdue":
            qs = qs.filter(due_date__lt=today)
        elif tab == "week":
            qs = qs.filter(due_date__lte=today + timedelta(days=7))
        else:
            qs = qs.filter(Q(due_date=today) | Q(due_date__lt=today) | Q(due_date__isnull=True))
        return qs.order_by("due_date", "-priority")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Мне на сегодня"
        ctx["tab"] = self.request.GET.get("tab", "today")
        today = timezone.now().date()
        ctx["today"] = today
        tasks = list(ctx.get("tasks") or ctx.get("object_list") or [])
        ctx["overdue_count"] = sum(1 for t in tasks if t.due_date and t.due_date < today)
        ctx["high_priority_count"] = sum(1 for t in tasks if t.priority == 1)
        ctx["no_due_count"] = sum(1 for t in tasks if not t.due_date)
        ctx["can_create"] = user_can(self.request.user, "M08", "create")
        ctx["can_change"] = user_can(self.request.user, "M08", "change")
        m = _ctx_membership(self)
        profile, _ = UserProfile.objects.get_or_create(user=self.request.user)
        ctx["today_widgets"] = studio.today_widgets_for_profile(profile)
        ctx["today_widget_catalog"] = studio.TODAY_WIDGETS
        ctx["inbox_preview"] = today_inbox_preview(
            self.request.user, m.subsystem
        )
        return ctx


class TodayWidgetsSaveView(ModulePermissionMixin, View):
    """#46 — сохранение набора виджетов «Мне на сегодня»."""

    module_code = "M08"
    required_action = "change"

    def post(self, request):
        if request.content_type.startswith("application/json"):
            try:
                payload = json.loads(request.body.decode() or "{}")
            except json.JSONDecodeError:
                return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)
            widget_ids = payload.get("widgets") or []
        else:
            widget_ids = request.POST.getlist("widgets")
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        widgets = studio.save_today_widgets(profile, widget_ids)
        if request.headers.get("Accept", "").startswith("application/json") or request.content_type.startswith(
            "application/json"
        ):
            return JsonResponse({"ok": True, "widgets": widgets})
        messages.success(request, "Настройки виджетов сохранены.")
        return redirect("platform-today")


class TaskFormModalView(ModulePermissionMixin, View):
    """Создание и редактирование задачи в модальном окне."""

    module_code = "M08"

    def _form_action(self, pk=None):
        if pk:
            return reverse("platform-task-form-modal-edit", kwargs={"pk": pk})
        return reverse("platform-task-form-modal")

    def get(self, request, pk=None):
        pk = pk or self.kwargs.get("pk")
        m = _ctx_membership(self)
        if pk:
            if not user_can(request.user, "M08", "change"):
                return JsonResponse({"error": "forbidden"}, status=403)
            task = get_object_or_404(TaskItem, pk=pk, subsystem=m.subsystem)
            form = TaskItemForm(instance=task, subsystem=m.subsystem)
            title = f"Задача: {task.title[:60]}"
        else:
            if not user_can(request.user, "M08", "create"):
                return JsonResponse({"error": "forbidden"}, status=403)
            form = TaskItemForm(subsystem=m.subsystem)
            title = "Новая задача"
        return render(
            request,
            "platform/workplace/_task_form_modal.html",
            {
                "form": form,
                "form_action": self._form_action(pk),
                "modal_title": title,
            },
        )

    def post(self, request, pk=None):
        pk = pk or self.kwargs.get("pk")
        m = _ctx_membership(self)
        if pk:
            if not user_can(request.user, "M08", "change"):
                return JsonResponse({"error": "forbidden"}, status=403)
            task = get_object_or_404(TaskItem, pk=pk, subsystem=m.subsystem)
            form = TaskItemForm(request.POST, instance=task, subsystem=m.subsystem)
        else:
            if not user_can(request.user, "M08", "create"):
                return JsonResponse({"error": "forbidden"}, status=403)
            form = TaskItemForm(request.POST, subsystem=m.subsystem)
            task = None
        if not form.is_valid():
            return render(
                request,
                "platform/workplace/_task_form_modal.html",
                {
                    "form": form,
                    "form_action": self._form_action(pk),
                    "modal_title": "Проверьте поля",
                },
                status=400,
            )
        obj = form.save(commit=False)
        obj.subsystem = m.subsystem
        if not pk:
            obj.assignee = obj.assignee or request.user
        obj.save()
        log_activity(
            m.subsystem,
            request.user,
            "обновил задачу" if pk else "создал задачу",
            obj.title,
            module_code="M08",
            link_path=reverse("platform-task-edit", kwargs={"pk": obj.pk}),
        )
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": True})
        return redirect("platform-today")


class TaskModalView(ModulePermissionMixin, View):
    module_code = "M08"

    def get(self, request, pk):
        m = _ctx_membership(self)
        task = get_object_or_404(TaskItem, pk=pk, subsystem=m.subsystem)
        return render(
            request,
            "platform/workplace/_task_modal.html",
            {
                "task": task,
                "can_change": user_can(request.user, "M08", "change"),
            },
        )


class TaskCompleteView(ModulePermissionMixin, View):
    module_code = "M08"
    required_action = "change"

    def post(self, request, pk):
        m = _ctx_membership(self)
        task = get_object_or_404(
            TaskItem, pk=pk, subsystem=m.subsystem, assignee=request.user
        )
        task.completed_at = timezone.now()
        task.kanban_column = TaskItem.KanbanColumn.DONE
        task.save(update_fields=["completed_at", "kanban_column"])
        log_activity(
            m.subsystem,
            request.user,
            "завершил задачу",
            task.title,
            module_code="M08",
            link_path=reverse("platform-task-edit", kwargs={"pk": task.pk}),
        )
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": True})
        messages.success(request, "Задача отмечена выполненной.")
        return redirect("platform-today")


class TaskCreateView(ModulePermissionMixin, CreateView):
    module_code = "M08"
    required_action = "create"
    model = TaskItem
    form_class = TaskItemForm
    template_name = "platform/workplace/task_form.html"
    success_url = reverse_lazy("platform-today")

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["subsystem"] = _ctx_membership(self).subsystem
        return kw

    def form_valid(self, form):
        m = _ctx_membership(self)
        form.instance.subsystem = m.subsystem
        form.instance.assignee = form.instance.assignee or self.request.user
        resp = super().form_valid(form)
        log_activity(
            m.subsystem,
            self.request.user,
            "создал задачу",
            form.instance.title,
            module_code="M08",
            link_path=reverse("platform-task-edit", kwargs={"pk": form.instance.pk}),
        )
        return resp

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Новая задача"
        return ctx


class TaskUpdateView(ModulePermissionMixin, UpdateView):
    module_code = "M08"
    required_action = "change"
    model = TaskItem
    form_class = TaskItemForm
    template_name = "platform/workplace/task_form.html"
    success_url = reverse_lazy("platform-today")

    def get_queryset(self):
        return TaskItem.objects.filter(subsystem=_ctx_membership(self).subsystem)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["subsystem"] = _ctx_membership(self).subsystem
        return kw

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Задача"
        return ctx


class CalendarView(ModulePermissionMixin, TemplateView):
    module_code = "M09"
    template_name = "platform/workplace/calendar.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Календарь"
        mine = self.request.GET.get("mine") == "1"
        qs = TaskItem.objects.filter(subsystem=m.subsystem).exclude(
            completed_at__isnull=False
        )
        if mine:
            qs = qs.filter(assignee=self.request.user)
        events = []
        for t in qs.select_related("case")[:300]:
            start = t.start_date or t.due_date
            if not start:
                continue
            end = t.gantt_end_date
            if not t.due_date and not t.start_date:
                label, bg, fg = "holiday", "#28c76f", "#ffffff"
            elif t.priority == 1:
                label, bg, fg = "personal", "#ff4c51", "#ffffff"
            elif t.priority == 2:
                label, bg, fg = "family", "#ff9f43", "#ffffff"
            else:
                label, bg, fg = "business", "#7367f0", "#ffffff"
            events.append(
                {
                    "id": str(t.pk),
                    "title": t.title,
                    "start": start.isoformat(),
                    "end": (end.isoformat() if end and end != start else None),
                    "url": reverse("platform-task-edit", kwargs={"pk": t.pk}),
                    "allDay": True,
                    "backgroundColor": bg,
                    "borderColor": bg,
                    "textColor": fg,
                    "classNames": [f"fc-event-{label}"],
                    "extendedProps": {
                        "calendar": label,
                        "case": t.case.number if t.case else "",
                        "priority": t.priority,
                    },
                }
            )
        ctx["events_json"] = json.dumps(events, ensure_ascii=False)
        ctx["filter_mine"] = mine
        return ctx


class KanbanView(ModulePermissionMixin, TemplateView):
    module_code = "M10"
    template_name = "platform/workplace/kanban.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Канбан"
        mine = self.request.GET.get("mine") == "1"
        qs = TaskItem.objects.filter(subsystem=m.subsystem, completed_at__isnull=True)
        if mine:
            qs = qs.filter(assignee=self.request.user)
        ctx["filter_mine"] = mine
        ctx["column_data"] = [
            {
                "code": col[0],
                "label": col[1],
                "tasks": qs.filter(kanban_column=col[0]).select_related("assignee", "case")[:50],
            }
            for col in TaskItem.KanbanColumn.choices
        ]
        ctx["can_change"] = user_can(self.request.user, "M10", "change")
        return ctx


class KanbanMoveView(ModulePermissionMixin, View):
    module_code = "M10"
    required_action = "change"

    def post(self, request, pk):
        m = _ctx_membership(self)
        task = get_object_or_404(TaskItem, pk=pk, subsystem=m.subsystem)
        col = request.POST.get("column")
        if col in dict(TaskItem.KanbanColumn.choices):
            task.kanban_column = col
            if col == TaskItem.KanbanColumn.DONE:
                task.completed_at = timezone.now()
            else:
                task.completed_at = None
            task.save(update_fields=["kanban_column", "completed_at"])
            log_activity(
                m.subsystem,
                request.user,
                f"перенёс задачу в «{dict(TaskItem.KanbanColumn.choices)[col]}»",
                task.title,
                module_code="M10",
            )
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": True, "column": col})
        return redirect("platform-kanban")


class GanttView(ModulePermissionMixin, TemplateView):
    module_code = "M11"
    template_name = "platform/workplace/gantt.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Планировщик (Гант)"
        mine = self.request.GET.get("mine") == "1"
        user = self.request.user if mine else None
        ctx["rows"] = gantt_rows(m.subsystem, user=user)
        ctx["filter_mine"] = mine
        ctx["can_change"] = user_can(self.request.user, "M11", "change")
        return ctx


class NotificationsView(ModulePermissionMixin, ListView):
    module_code = "M12"
    template_name = "platform/workplace/notifications.html"
    context_object_name = "notifications"
    paginate_by = 30

    def get_queryset(self):
        m = _ctx_membership(self)
        qs = Notification.objects.filter(user=self.request.user, subsystem=m.subsystem)
        level = self.request.GET.get("level")
        if level:
            qs = qs.filter(level=level)
        unread = self.request.GET.get("unread")
        if unread == "1":
            qs = qs.filter(is_read=False)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Уведомления"
        ctx["filter_level"] = self.request.GET.get("level", "")
        ctx["filter_unread"] = self.request.GET.get("unread", "")
        ctx["levels"] = Notification.Level.choices
        ctx["can_change"] = user_can(self.request.user, "M12", "change")
        return ctx


class NotificationReadView(ModulePermissionMixin, View):
    module_code = "M12"
    required_action = "change"

    def post(self, request, pk):
        m = _ctx_membership(self)
        n = get_object_or_404(Notification, pk=pk, user=request.user, subsystem=m.subsystem)
        n.is_read = True
        n.save(update_fields=["is_read"])
        if n.link:
            return redirect(n.link)
        return redirect("platform-notifications")


class NotificationReadAllView(ModulePermissionMixin, View):
    module_code = "M12"
    required_action = "change"

    def post(self, request):
        m = _ctx_membership(self)
        Notification.objects.filter(
            user=request.user, subsystem=m.subsystem, is_read=False
        ).update(is_read=True)
        messages.success(request, "Все уведомления прочитаны.")
        return redirect("platform-notifications")


class FavoritesView(ModulePermissionMixin, TemplateView):
    module_code = "M13"
    template_name = "platform/workplace/favorites.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        u = self.request.user
        ctx["page_title"] = "Избранное и фильтры"
        ctx["favorites"] = Favorite.objects.filter(user=u).filter(
            Q(subsystem=m.subsystem) | Q(subsystem__isnull=True)
        )
        ctx["saved_filters"] = SavedFilter.objects.filter(
            user=u
        ).filter(Q(subsystem=m.subsystem) | Q(subsystem__isnull=True))
        ctx["favorite_form"] = FavoriteForm()
        ctx["filter_form"] = SavedFilterForm()
        ctx["can_create"] = user_can(u, "M13", "create")
        ctx["can_delete"] = user_can(u, "M13", "delete")
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        action = request.POST.get("action")
        if action == "favorite" and user_can(request.user, "M13", "create"):
            form = FavoriteForm(request.POST)
            if form.is_valid():
                fav = form.save(commit=False)
                fav.user = request.user
                fav.subsystem = m.subsystem
                fav.save()
                messages.success(request, "Закладка добавлена.")
            else:
                messages.error(request, "Не удалось сохранить закладку.")
        elif action == "filter" and user_can(request.user, "M13", "create"):
            form = SavedFilterForm(request.POST)
            if form.is_valid():
                import json as _json

                try:
                    params = _json.loads(form.cleaned_data["params_json"] or "{}")
                except _json.JSONDecodeError:
                    messages.error(request, "Некорректный JSON параметров.")
                    return redirect("platform-favorites")
                SavedFilter.objects.create(
                    user=request.user,
                    subsystem=m.subsystem,
                    module_code=form.cleaned_data["module_code"],
                    name=form.cleaned_data["name"],
                    params=params,
                )
                messages.success(request, "Фильтр сохранён.")
            else:
                messages.error(request, "Проверьте форму фильтра.")
        return redirect("platform-favorites")


class FavoriteDeleteView(ModulePermissionMixin, View):
    module_code = "M13"
    required_action = "delete"

    def post(self, request, pk):
        m = _ctx_membership(self)
        fav = get_object_or_404(Favorite, pk=pk, user=request.user)
        if fav.subsystem_id and fav.subsystem_id != m.subsystem_id:
            return redirect("platform-favorites")
        fav.delete()
        messages.success(request, "Закладка удалена.")
        return redirect("platform-favorites")


class SavedFilterDeleteView(ModulePermissionMixin, View):
    module_code = "M13"
    required_action = "delete"

    def post(self, request, pk):
        m = _ctx_membership(self)
        sf = get_object_or_404(SavedFilter, pk=pk, user=request.user)
        if sf.subsystem_id and sf.subsystem_id != m.subsystem_id:
            return redirect("platform-favorites")
        sf.delete()
        messages.success(request, "Фильтр удалён.")
        return redirect("platform-favorites")


class ActivityView(ModulePermissionMixin, ListView):
    module_code = "M14"
    template_name = "platform/workplace/activity.html"
    context_object_name = "events"
    paginate_by = 50

    def get_queryset(self):
        m = _ctx_membership(self)
        qs = ActivityEvent.objects.filter(subsystem=m.subsystem).select_related("actor")
        module = self.request.GET.get("module", "").strip()
        if module:
            qs = qs.filter(module_code=module)
        mine = self.request.GET.get("mine") == "1"
        if mine:
            qs = qs.filter(actor=self.request.user)
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(target_repr__icontains=q) | Q(verb__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Лента активности"
        ctx["filter_module"] = self.request.GET.get("module", "")
        ctx["filter_mine"] = self.request.GET.get("mine") == "1"
        ctx["search_q"] = self.request.GET.get("q", "")
        base_qs = ActivityEvent.objects.filter(subsystem=m.subsystem)
        today = timezone.now().date()
        ctx["stats"] = {
            "total": base_qs.count(),
            "today": base_qs.filter(created_at__date=today).count(),
            "mine": base_qs.filter(actor=self.request.user).count(),
        }
        from django.db.models import Count

        ctx["module_stats"] = list(
            base_qs.exclude(module_code="")
            .values("module_code")
            .annotate(cnt=Count("id"))
            .order_by("-cnt")[:8]
        )
        return ctx
