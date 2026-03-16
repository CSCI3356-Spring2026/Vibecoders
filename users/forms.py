from django import forms

from .models import UserFile


class UserFileUploadForm(forms.ModelForm):
    title = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional title"}),
    )

    class Meta:
        model = UserFile
        fields = ["title", "file"]
        widgets = {
            "file": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }
