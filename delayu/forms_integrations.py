import json

from django import forms

from delayu.forms import BOOTSTRAP, SELECT, BootstrapFormMixin
from delayu.models import IntegrationEndpoint


class IntegrationEndpointForm(BootstrapFormMixin, forms.ModelForm):
    config_json = forms.CharField(
        label="Конфигурация (JSON)",
        required=False,
        widget=forms.Textarea(attrs={"class": BOOTSTRAP, "rows": 5}),
    )

    class Meta:
        model = IntegrationEndpoint
        fields = [
            "code",
            "name",
            "description",
            "endpoint_type",
            "is_active",
            "max_retries",
        ]
        widgets = {"endpoint_type": forms.Select(attrs={"class": SELECT})}

    def __init__(self, *args, **kwargs):
        instance = kwargs.get("instance")
        super().__init__(*args, **kwargs)
        if instance and instance.config:
            self.fields["config_json"].initial = json.dumps(
                instance.config, ensure_ascii=False, indent=2
            )

    def clean_config_json(self):
        raw = self.cleaned_data.get("config_json", "").strip()
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise forms.ValidationError(str(e)) from e
        if not isinstance(data, dict):
            raise forms.ValidationError("Ожидается JSON-объект.")
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.config = self.cleaned_data.get("config_json") or {}
        if commit:
            obj.save()
        return obj


class ApiKeyForm(BootstrapFormMixin, forms.Form):
    name = forms.CharField(label="Название ключа", max_length=128)
    rate_limit_per_hour = forms.IntegerField(
        label="Лимит запросов/час", min_value=10, initial=1000
    )


class SmevSendForm(BootstrapFormMixin, forms.Form):
    message_type = forms.CharField(
        label="Тип сообщения СМЭВ",
        initial="Request",
        widget=forms.TextInput(attrs={"class": BOOTSTRAP}),
    )
    body = forms.CharField(
        label="Тело (XML/JSON)",
        widget=forms.Textarea(attrs={"class": BOOTSTRAP, "rows": 4}),
    )


class ExternalSyncForm(BootstrapFormMixin, forms.Form):
    entity = forms.CharField(
        label="Сущность",
        initial="CaseFile",
        widget=forms.TextInput(attrs={"class": BOOTSTRAP}),
    )
    external_id = forms.CharField(
        label="ID во внешней системе",
        widget=forms.TextInput(attrs={"class": BOOTSTRAP}),
    )
