from django import forms

from delayu.forms import BOOTSTRAP, SELECT, BootstrapFormMixin, DatePickerInput
from delayu.models import AudioArchiveItem, CaseFile


class AudioUploadForm(BootstrapFormMixin, forms.ModelForm):
    recorded_at = forms.DateTimeField(
        label="Дата записи",
        required=False,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local", "class": BOOTSTRAP}),
    )

    class Meta:
        model = AudioArchiveItem
        fields = ["title", "case", "source_type", "duration_sec", "file", "retention_until"]
        widgets = {
            "source_type": forms.Select(attrs={"class": SELECT}),
            "case": forms.Select(attrs={"class": SELECT}),
            "retention_until": DatePickerInput(),
            "duration_sec": forms.NumberInput(attrs={"class": BOOTSTRAP}),
        }

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            self.fields["case"].queryset = CaseFile.objects.filter(
                subsystem=subsystem, is_archived=False
            )
            self.fields["case"].required = False
