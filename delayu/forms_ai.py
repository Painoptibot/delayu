from django import forms

from delayu.forms import BOOTSTRAP, SELECT, BootstrapFormMixin
from delayu.models import AiPolicy, CaseFile, KnowledgeArticle


class AiQuestionForm(BootstrapFormMixin, forms.Form):
    question = forms.CharField(
        label="Вопрос",
        widget=forms.Textarea(attrs={"class": BOOTSTRAP, "rows": 3}),
    )


class AiSearchForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(
        label="Поисковый запрос",
        widget=forms.TextInput(attrs={"class": BOOTSTRAP, "placeholder": "Смысл, тема, номер…"}),
    )


class KnowledgeArticleForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = KnowledgeArticle
        fields = ["title", "body", "tags", "is_published"]
        widgets = {"body": forms.Textarea(attrs={"class": BOOTSTRAP, "rows": 8})}


class CaseAiToolForm(BootstrapFormMixin, forms.Form):
    case = forms.ModelChoiceField(
        label="Дело",
        queryset=CaseFile.objects.none(),
        widget=forms.Select(attrs={"class": SELECT}),
    )

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            self.fields["case"].queryset = CaseFile.objects.filter(
                subsystem=subsystem, is_archived=False
            )


class ClassifyForm(BootstrapFormMixin, forms.Form):
    subject = forms.CharField(
        label="Тема обращения",
        widget=forms.TextInput(attrs={"class": BOOTSTRAP}),
    )


class NerForm(BootstrapFormMixin, forms.Form):
    text = forms.CharField(
        label="Текст",
        widget=forms.Textarea(attrs={"class": BOOTSTRAP, "rows": 4}),
    )


class AiPolicyForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = AiPolicy
        fields = ["model_name", "max_requests_per_day", "allow_pii", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"class": BOOTSTRAP, "rows": 3})}
