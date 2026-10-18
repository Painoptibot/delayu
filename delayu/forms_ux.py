import json

from django import forms

from delayu.forms import BootstrapFormMixin
from delayu.models import CustomerLicense, ModuleCatalog, OnboardingArticle, UserDashboardLayout


class CustomerLicenseForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = CustomerLicense
        fields = [
            "organization",
            "title",
            "seats",
            "valid_from",
            "valid_until",
            "support_until",
            "modules",
            "note",
        ]
        widgets = {
            "valid_from": forms.DateInput(attrs={"type": "date"}),
            "valid_until": forms.DateInput(attrs={"type": "date"}),
            "support_until": forms.DateInput(attrs={"type": "date"}),
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        from delayu.services.licenses import customer_choices

        self.fields["organization"].queryset = customer_choices(subsystem)
        self.fields["organization"].label = "Заказчик"
        self.fields["modules"].queryset = ModuleCatalog.objects.filter(is_active=True).order_by(
            "sort_order", "code"
        )
        self.fields["modules"].required = False
        self.fields["modules"].help_text = "Пустой список — лицензия на платформу целиком."
        self.fields["valid_until"].required = False
        self.fields["valid_until"].help_text = "Пусто — бессрочная лицензия."
        self.fields["support_until"].required = False
        self.fields["title"].required = False
        self.fields["title"].help_text = "Если пусто, подставится название заказчика."


class OnboardingArticleForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = OnboardingArticle
        fields = ["slug", "title", "body", "kind", "sort_order", "is_published"]


class DashboardLayoutForm(BootstrapFormMixin, forms.ModelForm):
    widgets_json = forms.CharField(
        label="Виджеты (JSON)",
        widget=forms.Textarea(attrs={"rows": 6}),
    )

    class Meta:
        model = UserDashboardLayout
        fields = ["name", "is_default"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["widgets_json"].initial = json.dumps(
                self.instance.widgets or [], ensure_ascii=False, indent=2
            )
        else:
            from delayu.services.ux import default_widgets

            self.fields["widgets_json"].initial = json.dumps(
                default_widgets(), ensure_ascii=False, indent=2
            )

    def clean_widgets_json(self):
        raw = self.cleaned_data.get("widgets_json", "[]")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(str(exc)) from exc
        if not isinstance(data, list):
            raise forms.ValidationError("Ожидается массив виджетов.")
        return data

    def save(self, commit=True):
        self.instance.widgets = self.cleaned_data["widgets_json"]
        return super().save(commit=commit)
