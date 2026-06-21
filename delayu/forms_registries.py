import json

from django import forms

from delayu.forms import BOOTSTRAP, BootstrapFormMixin
from delayu.models import RegistryType
from delayu.services.registries import parse_field_schema


class RegistryTypeForm(BootstrapFormMixin, forms.ModelForm):
    field_schema_json = forms.CharField(
        label="Схема полей (JSON)",
        widget=forms.Textarea(
            attrs={
                "class": BOOTSTRAP,
                "rows": 8,
                "placeholder": '[{"key": "name", "label": "Наименование", "required": true}]',
            }
        ),
    )

    class Meta:
        model = RegistryType
        fields = ["code", "name", "description", "is_active", "sort_order"]
        widgets = {
            "description": forms.Textarea(attrs={"class": BOOTSTRAP, "rows": 2}),
            "sort_order": forms.NumberInput(attrs={"class": BOOTSTRAP, "min": 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.field_schema:
            self.fields["field_schema_json"].initial = json.dumps(
                self.instance.field_schema, ensure_ascii=False, indent=2
            )
        else:
            self.fields["field_schema_json"].initial = json.dumps(
                [
                    {"key": "name", "label": "Наименование", "required": True},
                    {"key": "inn", "label": "ИНН", "required": False},
                ],
                ensure_ascii=False,
                indent=2,
            )

    def clean_field_schema_json(self):
        try:
            return parse_field_schema(self.cleaned_data["field_schema_json"])
        except (json.JSONDecodeError, ValueError) as exc:
            raise forms.ValidationError(str(exc)) from exc

    def save(self, commit=True):
        self.instance.field_schema = self.cleaned_data["field_schema_json"]
        return super().save(commit=commit)


class RegistryImportForm(BootstrapFormMixin, forms.Form):
    payload = forms.CharField(
        label="JSON-массив записей",
        widget=forms.Textarea(attrs={"class": BOOTSTRAP, "rows": 10}),
        help_text='Пример: [{"name": "ООО Ромашка", "inn": "7700000000"}]',
    )


def build_record_form(registry_type: RegistryType, data=None, initial=None):
    """Динамическая форма записи по field_schema / FormSchema M74."""
    from delayu.services.form_schemas import resolve_registry_schema

    fields = {}
    for spec in resolve_registry_schema(registry_type):
        key = spec["key"]
        fields[key] = forms.CharField(
            label=spec.get("label", key),
            required=bool(spec.get("required")),
            widget=forms.TextInput(attrs={"class": BOOTSTRAP}),
        )
    form_class = type(
        "RegistryRecordDynamicForm",
        (BootstrapFormMixin, forms.Form),
        fields,
    )
    if data is not None:
        return form_class(data)
    return form_class(initial=initial or {})
