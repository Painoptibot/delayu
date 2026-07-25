"""Forms for Odysseus M87 settings."""

from django import forms

from delayu.forms import BOOTSTRAP, SELECT, BootstrapFormMixin
from delayu.models_odysseus import OdysseusSettings


class OdysseusSettingsForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = OdysseusSettings
        fields = (
            "enabled",
            "base_url",
            "embed_mode",
            "pinned_ref",
            "upstream_url",
            "vendor_path",
            "auth_mode",
            "shared_secret",
            "timeout_s",
        )
        widgets = {
            "embed_mode": forms.Select(attrs={"class": SELECT}),
            "auth_mode": forms.Select(attrs={"class": SELECT}),
            "shared_secret": forms.PasswordInput(render_value=True, attrs={"class": BOOTSTRAP}),
        }
