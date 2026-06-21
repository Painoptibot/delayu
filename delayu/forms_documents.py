from django import forms

from delayu.forms import BOOTSTRAP, SELECT, BootstrapFormMixin
from delayu.models import CaseFile, DocumentFile


class DocumentWizardForm(BootstrapFormMixin, forms.Form):
    title = forms.CharField(label="Наименование", max_length=255)
    doc_type = forms.ChoiceField(
        label="Тип документа",
        choices=DocumentFile.DocType.choices,
        widget=forms.Select(attrs={"class": SELECT}),
    )
    description = forms.CharField(
        label="Описание",
        required=False,
        widget=forms.Textarea(attrs={"class": BOOTSTRAP, "rows": 2}),
    )
    case = forms.ModelChoiceField(
        label="Дело",
        queryset=CaseFile.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": SELECT}),
    )
    file = forms.FileField(label="Файл", widget=forms.FileInput(attrs={"class": BOOTSTRAP}))

    def __init__(self, *args, subsystem=None, **kwargs):
        self.subsystem = subsystem
        super().__init__(*args, **kwargs)
        from delayu.services.nsi_choices import apply_field

        apply_field(
            self, "doc_type", subsystem, "document_type", DocumentFile.DocType.choices
        )
        if subsystem:
            self.fields["case"].queryset = CaseFile.objects.filter(
                subsystem=subsystem, is_archived=False
            ).order_by("-updated_at")


class DocumentVersionForm(BootstrapFormMixin, forms.Form):
    file = forms.FileField(label="Новый файл", widget=forms.FileInput(attrs={"class": BOOTSTRAP}))
    title = forms.CharField(label="Наименование (опционально)", max_length=255, required=False)
