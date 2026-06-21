import json

from django import forms
from django.contrib.auth import get_user_model

from delayu.forms import BootstrapFormMixin
from delayu.models import (
    BulkOperation,
    CaseFile,
    ExportJob,
    FormSchema,
    ManagementDirective,
    NSIClassifier,
    NSIValue,
)

User = get_user_model()


class NSIClassifierForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = NSIClassifier
        fields = ["code", "name", "description", "is_active"]


class NSIValueForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = NSIValue
        fields = ["code", "name", "parent", "sort_order", "is_active"]

    def __init__(self, *args, classifier=None, **kwargs):
        super().__init__(*args, **kwargs)
        if classifier:
            self.fields["parent"].queryset = NSIValue.objects.filter(classifier=classifier)
            self.fields["parent"].required = False


class FormSchemaForm(BootstrapFormMixin, forms.ModelForm):
    schema_json = forms.CharField(
        label="Поля (JSON-массив)",
        widget=forms.Textarea(attrs={"rows": 8}),
        help_text='[{"key":"field1","label":"Поле","type":"text","required":true}]',
    )

    class Meta:
        model = FormSchema
        fields = ["target", "code", "name", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["schema_json"].initial = json.dumps(
                self.instance.schema or [], ensure_ascii=False, indent=2
            )
        else:
            self.fields["schema_json"].initial = "[]"

    def clean_schema_json(self):
        raw = self.cleaned_data.get("schema_json", "[]")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(f"Некорректный JSON: {exc}") from exc
        if not isinstance(data, list):
            raise forms.ValidationError("Ожидается JSON-массив полей.")
        return data

    def save(self, commit=True):
        self.instance.schema = self.cleaned_data["schema_json"]
        return super().save(commit=commit)


class BulkOperationForm(BootstrapFormMixin, forms.Form):
    operation = forms.ChoiceField(choices=BulkOperation.Operation.choices)
    status_filter = forms.ChoiceField(
        label="Фильтр по статусу дела",
        choices=[("", "Все")] + list(CaseFile.Status.choices),
        required=False,
    )
    new_status = forms.ChoiceField(
        label="Новый статус",
        choices=CaseFile.Status.choices,
        required=False,
    )
    assignee = forms.ModelChoiceField(
        label="Исполнитель",
        queryset=User.objects.none(),
        required=False,
    )

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            from delayu.models import SubsystemMembership

            user_ids = SubsystemMembership.objects.filter(subsystem=subsystem).values_list(
                "user_id", flat=True
            )
            self.fields["assignee"].queryset = User.objects.filter(pk__in=user_ids)


class ExportJobForm(BootstrapFormMixin, forms.Form):
    kind = forms.ChoiceField(
        label="Тип выгрузки",
        choices=[
            ("cases_csv", "Дела (CSV)"),
            ("registry_csv", "Реестр (CSV)"),
            ("print_batch", "Пакет печати"),
        ],
    )
    title = forms.CharField(max_length=255, required=False)


class ManagementDirectiveForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ManagementDirective
        fields = [
            "number",
            "title",
            "instruction",
            "assignee",
            "case",
            "due_date",
            "status",
        ]

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            from delayu.models import SubsystemMembership

            user_ids = SubsystemMembership.objects.filter(subsystem=subsystem).values_list(
                "user_id", flat=True
            )
            self.fields["assignee"].queryset = User.objects.filter(pk__in=user_ids)
            self.fields["case"].queryset = CaseFile.objects.filter(subsystem=subsystem).order_by(
                "-updated_at"
            )[:200]
            self.fields["case"].required = False


class DirectiveReportForm(BootstrapFormMixin, forms.Form):
    report_text = forms.CharField(label="Отчёт исполнителя", widget=forms.Textarea(attrs={"rows": 4}))
