import json

from django import forms

from delayu.forms import BOOTSTRAP, SELECT, BootstrapFormMixin, DatePickerInput
from delayu.models import ReportSchedule, ReportTemplate, RegulatoryReportSubmission
from delayu.services.analytics import REPORT_QUERY_KEYS


class ReportTemplateForm(BootstrapFormMixin, forms.ModelForm):
    columns_json = forms.CharField(
        label="Колонки (JSON-массив)",
        required=False,
        widget=forms.Textarea(attrs={"class": BOOTSTRAP, "rows": 2}),
        initial="[]",
    )

    class Meta:
        model = ReportTemplate
        fields = [
            "code",
            "name",
            "query_key",
            "report_kind",
            "description",
            "is_active",
            "default_period_days",
        ]
        widgets = {
            "query_key": forms.Select(attrs={"class": SELECT}),
            "report_kind": forms.Select(attrs={"class": SELECT}),
            "description": forms.Textarea(attrs={"class": BOOTSTRAP, "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["query_key"].choices = [(k, v) for k, v in REPORT_QUERY_KEYS.items()]
        if self.instance.pk and self.instance.columns:
            self.fields["columns_json"].initial = json.dumps(
                self.instance.columns, ensure_ascii=False
            )

    def clean_columns_json(self):
        raw = self.cleaned_data.get("columns_json") or "[]"
        try:
            val = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError("Некорректный JSON") from exc
        if not isinstance(val, list):
            raise forms.ValidationError("Ожидается JSON-массив")
        return val

    def save(self, commit=True):
        self.instance.columns = self.cleaned_data["columns_json"]
        return super().save(commit=commit)


class ReportScheduleForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ReportSchedule
        fields = [
            "template",
            "frequency",
            "run_hour",
            "run_weekday",
            "run_day",
            "period_days",
            "is_active",
        ]
        widgets = {
            "template": forms.Select(attrs={"class": SELECT}),
            "frequency": forms.Select(attrs={"class": SELECT}),
        }

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            self.fields["template"].queryset = ReportTemplate.objects.filter(
                subsystem=subsystem, is_active=True
            )


class RegulatorySubmissionForm(BootstrapFormMixin, forms.ModelForm):
    indicators_json = forms.CharField(
        label="Показатели (JSON)",
        widget=forms.Textarea(attrs={"class": BOOTSTRAP, "rows": 4}),
        initial='{"cases_closed": 0, "appeals_received": 0}',
    )

    class Meta:
        model = RegulatoryReportSubmission
        fields = [
            "form_code",
            "form_name",
            "period_label",
            "period_start",
            "period_end",
            "version",
        ]
        widgets = {
            "period_start": DatePickerInput(),
            "period_end": DatePickerInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.indicators:
            self.fields["indicators_json"].initial = json.dumps(
                self.instance.indicators, ensure_ascii=False, indent=2
            )

    def clean_indicators_json(self):
        raw = self.cleaned_data.get("indicators_json") or "{}"
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError("Некорректный JSON") from exc

    def save(self, commit=True):
        self.instance.indicators = self.cleaned_data["indicators_json"]
        return super().save(commit=commit)
