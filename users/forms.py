from django import forms

from .models import AdminProfile, StudentProfile, UserFile


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


class GenderOtherRequiredMixin:
    def clean(self):
        cleaned_data = super().clean()
        gender = (cleaned_data.get("gender") or "").strip().lower()
        gender_other = (cleaned_data.get("gender_other") or "").strip()
        if gender == "other" and not gender_other:
            self.add_error("gender_other", "Please share your gender or choose another option.")
        if gender != "other" and gender_other:
            cleaned_data["gender_other"] = ""
        return cleaned_data


class BaseProfileForm(GenderOtherRequiredMixin, forms.ModelForm):
    completion_fields = ()
    field_labels = {
        "gender": "Gender",
        "gender_other": "Other (please specify)",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, label in self.field_labels.items():
            if field_name in self.fields:
                self.fields[field_name].label = label
        for field_name in self.completion_fields:
            if field_name in self.fields:
                self.fields[field_name].required = True


class StudentProfileForm(BaseProfileForm):
    completion_fields = (
        "preferred_name",
        "age",
        "gender",
        "major",
        "bio",
        "messy_level",
        "guest_level",
        "bedtime",
        "noise_level",
        "drink",
        "party",
    )

    class Meta:
        model = StudentProfile
        fields = [
            "preferred_name",
            "age",
            "gender",
            "gender_other",
            "major",
            "bio",
            "messy_level",
            "guest_level",
            "bedtime",
            "noise_level",
            "smoke",
            "drink",
            "party",
            "pets",
        ]
        widgets = {
            "preferred_name": forms.TextInput(attrs={"class": "form-control"}),
            "age": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "gender": forms.Select(attrs={"class": "form-select"}),
            "gender_other": forms.TextInput(attrs={"class": "form-control", "placeholder": "Please specify"}),
            "major": forms.TextInput(attrs={"class": "form-control"}),
            "bio": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "messy_level": forms.NumberInput(attrs={"class": "form-range", "type": "range", "min": 1, "max": 5}),
            "guest_level": forms.NumberInput(attrs={"class": "form-range", "type": "range", "min": 1, "max": 5}),
            "bedtime": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "noise_level": forms.NumberInput(attrs={"class": "form-range", "type": "range", "min": 1, "max": 5}),
            "smoke": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "drink": forms.NumberInput(attrs={"class": "form-range", "type": "range", "min": 1, "max": 5}),
            "party": forms.NumberInput(attrs={"class": "form-range", "type": "range", "min": 1, "max": 5}),
            "pets": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class AdminProfileForm(BaseProfileForm):
    completion_fields = ("preferred_name", "age", "gender", "bio")

    class Meta:
        model = AdminProfile
        fields = [
            "preferred_name",
            "age",
            "gender",
            "gender_other",
            "bio",
        ]
        widgets = {
            "preferred_name": forms.TextInput(attrs={"class": "form-control"}),
            "age": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "gender": forms.Select(attrs={"class": "form-select"}),
            "gender_other": forms.TextInput(attrs={"class": "form-control", "placeholder": "Please specify"}),
            "bio": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }
