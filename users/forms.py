from django import forms

from .models import UserFile


class GoogleLoginAcceptanceForm(forms.Form):
    accept_terms = forms.BooleanField(
        required=True,
        label="I agree to the Terms of Service",
        error_messages={"required": "You must agree to the Terms of Service."},
    )
    accept_privacy = forms.BooleanField(
        required=True,
        label="I acknowledge the Privacy Policy",
        error_messages={"required": "You must acknowledge the Privacy Policy."},
    )


class UserFileUploadForm(forms.ModelForm):
    title = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional title"}),
    )

    class Meta:
        model = UserFile
        fields = ["title", "file"]
        widgets = {
            "file": forms.ClearableFileInput(
                attrs={"class": "form-control", "accept": ".pdf,.txt,.doc,.docx,.jpg,.jpeg,.png,.webp"}
            ),
        }
