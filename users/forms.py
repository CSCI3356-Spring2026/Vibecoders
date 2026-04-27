from django import forms

from .models import AdminProfile, Role, StudentProfile, UserFile, UserReport
from .validators import validate_avatar_upload


def _format_hour_label(hour):
    suffix = "AM" if hour < 12 else "PM"
    display_hour = hour % 12 or 12
    return f"{display_hour}:00 {suffix}"


BEDTIME_CHOICES = [("", "Select a time")] + [(hour, _format_hour_label(hour)) for hour in range(24)]


class GoogleLoginAcceptanceForm(forms.Form):
    reviewed_terms = forms.BooleanField(required=False, widget=forms.HiddenInput())
    reviewed_privacy = forms.BooleanField(required=False, widget=forms.HiddenInput())
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

    def __init__(self, *args, require_review=False, **kwargs):
        self.require_review = require_review
        super().__init__(*args, **kwargs)
        if self.require_review:
            self.fields["accept_terms"].widget.attrs.update(
                {"disabled": "disabled", "data-legal-review-checkbox": "terms"}
            )
            self.fields["accept_privacy"].widget.attrs.update(
                {"disabled": "disabled", "data-legal-review-checkbox": "privacy"}
            )
            self.fields["reviewed_terms"].widget.attrs.update({"data-legal-review-hidden": "terms"})
            self.fields["reviewed_privacy"].widget.attrs.update({"data-legal-review-hidden": "privacy"})

    def clean(self):
        cleaned_data = super().clean()
        if not self.require_review:
            return cleaned_data
        if not cleaned_data.get("reviewed_terms"):
            self.add_error("accept_terms", "Scroll through the Terms of Service before accepting.")
        if not cleaned_data.get("reviewed_privacy"):
            self.add_error("accept_privacy", "Scroll through the Privacy Policy before accepting.")
        return cleaned_data


class UserFileUploadForm(forms.ModelForm):
    title = forms.CharField(
        required=False,
        max_length=UserFile._meta.get_field("title").max_length,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional title"}),
    )

    class Meta:
        model = UserFile
        fields = ["title", "file"]
        widgets = {
            "file": forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".pdf,.jpg,.jpeg,.png,.webp"}),
        }


class AdminUserRoleForm(forms.Form):
    role = forms.ChoiceField(
        choices=Role.choices,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )


class SupportInvestigationForm(forms.Form):
    reason = forms.CharField(
        max_length=500,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Why does this account need sensitive review access?",
            }
        ),
    )


class UserReportForm(forms.ModelForm):
    class Meta:
        model = UserReport
        fields = ["reason", "details"]
        widgets = {
            "reason": forms.Select(attrs={"class": "form-select"}),
            "details": forms.Textarea(
                attrs={
                    "rows": 4,
                    "class": "form-control",
                    "placeholder": "Tell the admin team what happened with this user.",
                }
            ),
        }
        labels = {
            "reason": "Reason",
            "details": "Details",
        }

    def clean(self):
        cleaned_data = super().clean()
        details = (cleaned_data.get("details") or "").strip()
        reason = cleaned_data.get("reason")
        if reason == UserReport.REASON_OTHER and not details:
            self.add_error("details", "Add context so the admin team can review this report.")
        if len(details) > 2000:
            self.add_error("details", "Keep report details to 2,000 characters or fewer.")
        cleaned_data["details"] = details
        return cleaned_data


class AdminUserReportResolutionForm(forms.Form):
    ENFORCEMENT_NONE = "none"
    ENFORCEMENT_WARN = "warn"
    ENFORCEMENT_RESTRICT_ROOMMATE = "restrict_roommate"
    ENFORCEMENT_DEACTIVATE = "deactivate"
    ENFORCEMENT_CHOICES = [
        (ENFORCEMENT_NONE, "No enforcement action"),
        (ENFORCEMENT_WARN, "Warn user"),
        (ENFORCEMENT_RESTRICT_ROOMMATE, "Restrict roommate access"),
        (ENFORCEMENT_DEACTIVATE, "Deactivate account"),
    ]

    status = forms.ChoiceField(
        choices=UserReport.STATUS_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    enforcement_action = forms.ChoiceField(
        choices=ENFORCEMENT_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    resolution_notes = forms.CharField(
        required=False,
        label="Moderator notes",
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "class": "form-control",
                "placeholder": "Document what was reviewed and how the report was handled.",
            }
        ),
    )

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)
        if instance is not None and not self.is_bound:
            self.initial.setdefault("status", instance.status)
            self.initial.setdefault("enforcement_action", self.ENFORCEMENT_NONE)
            self.initial.setdefault("resolution_notes", instance.resolution_notes)

    def clean_resolution_notes(self):
        notes = (self.cleaned_data.get("resolution_notes") or "").strip()
        if len(notes) > 2000:
            raise forms.ValidationError("Keep moderator notes to 2,000 characters or fewer.")
        return notes

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get("status")
        enforcement_action = cleaned_data.get("enforcement_action") or self.ENFORCEMENT_NONE
        resolution_notes = cleaned_data.get("resolution_notes") or ""
        if (
            enforcement_action != self.ENFORCEMENT_NONE
            or status in {UserReport.STATUS_RESOLVED, UserReport.STATUS_DISMISSED}
        ) and not resolution_notes.strip():
            self.add_error("resolution_notes", "Add moderator notes when applying enforcement or closing a report.")
        cleaned_data["enforcement_action"] = enforcement_action
        return cleaned_data


class AvatarUploadForm(forms.Form):
    avatar = forms.ImageField(
        validators=[validate_avatar_upload],
        widget=forms.ClearableFileInput(
            attrs={"accept": "image/jpeg,image/png,image/webp", "class": "avatar-upload-input"}
        ),
    )


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
        "preferred_name": "Display name",
        "age": "Age",
        "gender": "Gender",
        "gender_other": "Other (please specify)",
        "bio": "Short intro",
    }
    field_help_texts = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, label in self.field_labels.items():
            if field_name in self.fields:
                self.fields[field_name].label = label
        for field_name, help_text in self.field_help_texts.items():
            if field_name in self.fields:
                self.fields[field_name].help_text = help_text
        for field_name in self.completion_fields:
            if field_name in self.fields:
                self.fields[field_name].required = True


class StudentProfileForm(BaseProfileForm):
    bedtime = forms.TypedChoiceField(
        choices=BEDTIME_CHOICES,
        coerce=int,
        empty_value=None,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
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
    field_labels = BaseProfileForm.field_labels | {
        "major": "Major or program",
        "messy_level": "Cleanliness preference",
        "guest_level": "Guest frequency",
        "bedtime": "Typical bedtime",
        "noise_level": "Noise tolerance",
        "smoke": "Smoking okay",
        "drink": "Drinking",
        "party": "Social scene",
        "pets": "Pets okay",
    }
    field_help_texts = {
        "preferred_name": "Shown on your profile, messages, and roommate matches.",
        "age": "Used on your roommate profile.",
        "gender": "Shown on your roommate profile.",
        "major": "Helpful context for potential roommates.",
        "bio": "A short introduction about how you live and what you are looking for.",
        "messy_level": "Pick the option that feels closest to your shared-space standard.",
        "guest_level": "How often you are comfortable having guests around.",
        "bedtime": "Choose the closest time you usually wind down.",
        "noise_level": "How much sound feels normal in your home.",
        "smoke": "Turn this on if smoking is okay in your home search.",
        "drink": "How often drinking is part of your routine.",
        "party": "How social or nightlife-oriented your home feels.",
        "pets": "Turn this on if pets are welcome in your housing plans.",
    }

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
            "preferred_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "How your name should appear",
                    "autocomplete": "nickname",
                }
            ),
            "age": forms.NumberInput(attrs={"class": "form-control", "min": 16, "max": 99, "placeholder": "Age"}),
            "gender": forms.Select(attrs={"class": "form-select"}),
            "gender_other": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "How you want this shown on your profile"}
            ),
            "major": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Computer Science, Finance, Nursing..."}
            ),
            "bio": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Share a quick sense of your routine, habits, and the kind of home you want.",
                }
            ),
            "messy_level": forms.RadioSelect(attrs={"class": "profile-scale-input"}),
            "guest_level": forms.RadioSelect(attrs={"class": "profile-scale-input"}),
            "noise_level": forms.RadioSelect(attrs={"class": "profile-scale-input"}),
            "smoke": forms.CheckboxInput(attrs={"class": "profile-toggle-input"}),
            "drink": forms.RadioSelect(attrs={"class": "profile-scale-input"}),
            "party": forms.RadioSelect(attrs={"class": "profile-scale-input"}),
            "pets": forms.CheckboxInput(attrs={"class": "profile-toggle-input"}),
        }


class AdminProfileForm(BaseProfileForm):
    completion_fields = ("preferred_name", "bio")
    field_labels = BaseProfileForm.field_labels | {
        "age": "Age (optional)",
        "bio": "About this account",
    }
    field_help_texts = {
        "preferred_name": "Shown on your listings, messages, and account surfaces.",
        "gender": "Optional profile detail.",
        "bio": "A short description of who you are or what you manage.",
    }

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
            "preferred_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "How this account should appear",
                    "autocomplete": "nickname",
                }
            ),
            "age": forms.NumberInput(attrs={"class": "form-control", "min": 16, "max": 99, "placeholder": "Optional"}),
            "gender": forms.Select(attrs={"class": "form-select"}),
            "gender_other": forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional"}),
            "bio": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Briefly describe who you are, what you manage, or what renters should know.",
                }
            ),
        }
