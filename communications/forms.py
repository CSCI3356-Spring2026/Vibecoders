from django import forms

from .models import MESSAGE_BODY_MAX_LENGTH, ListingMessage


class ConversationMessageForm(forms.ModelForm):
    class Meta:
        model = ListingMessage
        fields = ["body"]
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "maxlength": MESSAGE_BODY_MAX_LENGTH,
                    "placeholder": "Ask about timing, availability, rent, or next steps.",
                }
            )
        }
