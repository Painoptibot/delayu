from django import forms

from delayu.forms import BootstrapFormMixin
from delayu.models import (
    CitizenAppeal,
    DataDataset,
    EtlJob,
    GeoLayer,
    GeoObject,
    SsoProvider,
)


class GeoLayerForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = GeoLayer
        fields = ["code", "name", "color", "is_visible"]


class GeoObjectForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = GeoObject
        fields = ["layer", "case", "title", "address", "latitude", "longitude"]

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["latitude"].required = False
        self.fields["longitude"].required = False
        if subsystem:
            self.fields["layer"].queryset = GeoLayer.objects.filter(subsystem=subsystem)
            from delayu.models import CaseFile

            self.fields["case"].queryset = CaseFile.objects.filter(subsystem=subsystem).order_by(
                "-updated_at"
            )[:200]
            self.fields["case"].required = False

    def clean(self):
        cleaned = super().clean()
        from delayu.services import infra

        if cleaned.get("address") and not cleaned.get("latitude"):
            lat, lng = infra.demo_geocode(cleaned["address"])
            cleaned["latitude"] = lat
            cleaned["longitude"] = lng
        return cleaned


class SsoProviderForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = SsoProvider
        fields = ["name", "provider_type", "client_id", "is_active", "metadata"]


class EtlJobForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = EtlJob
        fields = ["name", "source_type", "schedule_cron", "is_active"]


class DataDatasetForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = DataDataset
        fields = ["name", "slug", "description", "is_published", "row_count", "schema"]


class CitizenAppealForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = CitizenAppeal
        fields = ["public_id", "applicant_name", "subject", "status", "case"]

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            from delayu.models import CaseFile

            self.fields["case"].queryset = CaseFile.objects.filter(subsystem=subsystem).order_by(
                "-updated_at"
            )[:200]
            self.fields["case"].required = False
