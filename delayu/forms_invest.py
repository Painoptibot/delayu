"""Forms for invest subsystem screens."""

from django import forms
from django.contrib.auth import get_user_model

from delayu.models import SubsystemMembership
from delayu.models_invest import InvestProject

User = get_user_model()


class InvestProjectForm(forms.ModelForm):
    """Project form intentionally omits funnel; the current funnel is display-only."""

    class Meta:
        model = InvestProject
        fields = [
            "organization",
            "code",
            "name",
            "investor_name",
            "industry",
            "stage",
            "owner",
            "investment_amount",
            "jobs_count",
        ]
        widgets = {
            "stage": forms.TextInput(attrs={"placeholder": "lead"}),
            "investment_amount": forms.NumberInput(attrs={"step": "0.01"}),
        }

    def __init__(self, *args, membership=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.membership = membership
        subsystem = membership.subsystem if membership else getattr(self.instance, "subsystem", None)
        if subsystem:
            self.fields["organization"].queryset = subsystem.organizations.filter(is_active=True)
            self.fields["owner"].queryset = User.objects.filter(
                subsystem_memberships__subsystem=subsystem
            ).distinct()
        self.fields["owner"].required = False
        self.fields["investor_name"].required = False
        self.fields["industry"].required = False
        self.fields["investment_amount"].required = False
        self.fields["jobs_count"].required = False

    @property
    def display_funnel(self):
        value = self.instance.funnel or InvestProject.Funnel.ATTRACTION
        return InvestProject.Funnel(value).label

    def clean_organization(self):
        organization = self.cleaned_data["organization"]
        if self.membership and organization.subsystem_id != self.membership.subsystem_id:
            raise forms.ValidationError("Организация должна относиться к активному инвестконтуру.")
        return organization
