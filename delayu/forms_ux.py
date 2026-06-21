import json

from django import forms

from delayu.forms import BootstrapFormMixin
from delayu.models import OnboardingArticle, UserDashboardLayout


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
