from django import forms
from django.contrib.auth import get_user_model

from delayu.models import (
    CaseFile,
    ChatMessage,
    Correspondence,
    DocumentFile,
    RegistryRecord,
    Role,
    Subsystem,
    SubsystemMembership,
    TaskItem,
)

User = get_user_model()

BOOTSTRAP = "form-control"
SELECT = "form-select"
DATE_PICKER_CLASS = "form-control delayu-date"


class DatePickerInput(forms.DateInput):
    """Поле даты с flatpickr (как в шаблоне Materialize)."""

    input_type = "text"

    def __init__(self, attrs=None):
        base = {"class": DATE_PICKER_CLASS, "placeholder": "дд.мм.гггг", "autocomplete": "off"}
        if attrs:
            base.update(attrs)
        super().__init__(attrs=base)


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            w = field.widget
            if isinstance(w, (forms.CheckboxInput, forms.RadioSelect)):
                w.attrs.setdefault("class", "form-check-input")
            elif isinstance(w, forms.Select):
                w.attrs.setdefault("class", SELECT)
            elif isinstance(w, forms.Textarea):
                w.attrs.setdefault("class", BOOTSTRAP)
                w.attrs.setdefault("rows", 3)
            else:
                w.attrs.setdefault("class", BOOTSTRAP)


class SubsystemForm(BootstrapFormMixin, forms.ModelForm):
    module_codes = forms.MultipleChoiceField(
        label="Модули",
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "list-unstyled"}),
    )

    class Meta:
        model = Subsystem
        fields = ["code", "name", "description", "status", "primary_color"]
        widgets = {
            "primary_color": forms.TextInput(attrs={"type": "color"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from delayu.models import ModuleCatalog

        choices = [(m.code, f"{m.code} — {m.name}") for m in ModuleCatalog.objects.filter(is_active=True)]
        self.fields["module_codes"].choices = choices
        if self.instance.pk:
            enabled = self.instance.module_links.filter(enabled=True).values_list(
                "module__code", flat=True
            )
            self.fields["module_codes"].initial = list(enabled)
        else:
            self.fields["module_codes"].initial = [c[0] for c in choices]

    def save_modules(self, subsystem):
        from delayu.models import ModuleCatalog, SubsystemModule

        selected = set(self.cleaned_data.get("module_codes") or [])
        for mod in ModuleCatalog.objects.filter(is_active=True):
            link, _ = SubsystemModule.objects.update_or_create(
                subsystem=subsystem, module=mod, defaults={"enabled": mod.code in selected}
            )


class CorrespondenceForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Correspondence
        fields = [
            "direction",
            "reg_number",
            "reg_date",
            "subject",
            "counterparty",
            "assignee",
            "status",
        ]
        widgets = {"reg_date": forms.DateInput(attrs={"type": "date"})}


class TaskItemForm(BootstrapFormMixin, forms.ModelForm):
    TASK_PRIORITY = (
        (1, "Высокий"),
        (2, "Средний"),
        (3, "Обычный"),
    )

    class Meta:
        model = TaskItem
        fields = [
            "title",
            "description",
            "assignee",
            "due_date",
            "start_date",
            "duration_days",
            "priority",
            "kanban_column",
            "case",
        ]
        labels = {
            "title": "Название",
            "description": "Описание",
            "assignee": "Исполнитель",
            "due_date": "Срок",
            "start_date": "Дата начала",
            "duration_days": "Длительность (дней)",
            "priority": "Приоритет",
            "kanban_column": "Колонка канбана",
            "case": "Дело",
        }
        widgets = {
            "due_date": DatePickerInput(),
            "start_date": DatePickerInput(),
            "description": forms.Textarea(attrs={"rows": 3, "class": BOOTSTRAP}),
            "priority": forms.Select(attrs={"class": SELECT}),
            "kanban_column": forms.Select(attrs={"class": SELECT}),
        }

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        from delayu.services.nsi_choices import apply_field

        apply_field(
            self,
            "priority",
            subsystem,
            "task_priority",
            self.TASK_PRIORITY,
            cast=int,
        )
        apply_field(
            self,
            "kanban_column",
            subsystem,
            "kanban_column",
            TaskItem.KanbanColumn.choices,
        )
        if subsystem:
            from django.contrib.auth import get_user_model

            User = get_user_model()
            self.fields["assignee"].queryset = User.objects.filter(
                subsystem_memberships__subsystem=subsystem
            ).distinct()
            self.fields["case"].queryset = CaseFile.objects.filter(
                subsystem=subsystem, is_archived=False
            )
            self.fields["case"].required = False


class DocumentUploadForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = DocumentFile
        fields = ["title", "file", "case"]


class ChatMessageForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ChatMessage
        fields = ["body"]
        widgets = {
            "body": forms.Textarea(
                attrs={"class": "form-control", "rows": 2, "placeholder": "Сообщение…"}
            )
        }


class MembershipForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = SubsystemMembership
        fields = ["user", "organization", "role", "is_default"]

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            self.fields["organization"].queryset = subsystem.organizations.all()
            self.fields["role"].queryset = subsystem.roles.all()
