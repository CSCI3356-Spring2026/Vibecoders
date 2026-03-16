from django import forms

from users.models import UserFile


class UserFileUploadForm(forms.ModelForm):
    class Meta:
        model = UserFile
        fields = ["title", "file"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Title"}),
            "file": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }
