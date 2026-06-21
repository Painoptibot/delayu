from django import forms
from django.contrib.auth import get_user_model

from delayu.forms import BOOTSTRAP, SELECT, BootstrapFormMixin
from delayu.models import (
    CaseFile,
    ChatRoom,
    DocumentFile,
    MessengerChannel,
    ObjectSubscription,
    VideoMeeting,
)

User = get_user_model()


class ChatRoomForm(BootstrapFormMixin, forms.ModelForm):
    members = forms.ModelMultipleChoiceField(
        label="Участники",
        queryset=User.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": SELECT, "size": 6}),
    )

    class Meta:
        model = ChatRoom
        fields = ["name", "case"]

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            self.fields["members"].queryset = User.objects.filter(
                subsystem_memberships__subsystem=subsystem
            ).distinct()
            self.fields["case"].queryset = CaseFile.objects.filter(
                subsystem=subsystem, is_archived=False
            )
            self.fields["case"].widget.attrs["class"] = SELECT
            self.fields["case"].required = False


class CommentHubForm(BootstrapFormMixin, forms.Form):
    body = forms.CharField(
        label="Комментарий",
        widget=forms.Textarea(
            attrs={"class": BOOTSTRAP, "rows": 3, "placeholder": "Текст, @username для упоминания"}
        ),
    )
    case = forms.ModelChoiceField(
        label="Дело",
        queryset=CaseFile.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": SELECT}),
    )

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            self.fields["case"].queryset = CaseFile.objects.filter(
                subsystem=subsystem, is_archived=False
            )


class SubscriptionForm(BootstrapFormMixin, forms.Form):
    target_type = forms.ChoiceField(
        label="Тип объекта",
        choices=ObjectSubscription.TargetType.choices,
        widget=forms.Select(attrs={"class": SELECT}),
    )
    case = forms.ModelChoiceField(
        label="Дело",
        queryset=CaseFile.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": SELECT}),
    )
    document = forms.ModelChoiceField(
        label="Документ",
        queryset=DocumentFile.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": SELECT}),
    )

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            self.fields["case"].queryset = CaseFile.objects.filter(
                subsystem=subsystem, is_archived=False
            )
            self.fields["document"].queryset = DocumentFile.objects.filter(
                subsystem=subsystem, is_current=True
            )[:200]


class VideoMeetingForm(BootstrapFormMixin, forms.ModelForm):
    scheduled_at = forms.DateTimeField(
        label="Дата и время",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local", "class": BOOTSTRAP}),
    )

    class Meta:
        model = VideoMeeting
        fields = ["title", "meeting_url", "scheduled_at", "case", "protocol_notes"]
        widgets = {"protocol_notes": forms.Textarea(attrs={"class": BOOTSTRAP, "rows": 3})}

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            self.fields["case"].queryset = CaseFile.objects.filter(
                subsystem=subsystem, is_archived=False
            )
            self.fields["case"].widget.attrs["class"] = SELECT
            self.fields["case"].required = False


class MessengerChannelForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = MessengerChannel
        fields = ["code", "name", "channel_type", "webhook_url", "is_active", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"class": BOOTSTRAP, "rows": 2})}
