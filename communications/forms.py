from django import forms

from .models import MESSAGE_BODY_MAX_LENGTH, ListingMessage


class ConversationMessageForm(forms.ModelForm):
    body = forms.CharField(
        max_length=MESSAGE_BODY_MAX_LENGTH,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 4,
                "maxlength": MESSAGE_BODY_MAX_LENGTH,
                "placeholder": "Ask about timing, availability, rent, or next steps.",
            }
        ),
    )

    class Meta:
        model = ListingMessage
        fields = ["body"]
