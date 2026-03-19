from django import forms

from .models import Listing


class ListingForm(forms.ModelForm):
    DEFAULTED_FIELDS = ("rooms", "bathrooms", "property_type")
    UTILITY_CHOICES = [
        ("Water", "Water"),
        ("Gas", "Gas"),
        ("WiFi", "WiFi"),
        ("Electricity", "Electricity"),
        ("Trash", "Trash"),
    ]
    common_utilities = forms.MultipleChoiceField(
        choices=UTILITY_CHOICES,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        required=False,
        label="Common Utilities",
    )
    other_utilities = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Other utilities...", "class": "form-control"}),
        label="Other",
    )
    images = forms.FileField(widget=forms.FileInput(), required=False)

    class Meta:
        model = Listing
        exclude = ["owner", "is_hidden", "created_at", "status", "utilities_included"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "bathrooms": forms.NumberInput(attrs={"step": "0.5", "min": "0"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["images"].widget.attrs.update({"multiple": True, "accept": ".jpg,.jpeg,.png,.webp,image/*"})
        for field_name in self.DEFAULTED_FIELDS:
            self.fields[field_name].required = False
            if not self.is_bound:
                self.fields[field_name].initial = Listing._meta.get_field(field_name).get_default()

        for field_name, field in self.fields.items():
            if field_name not in ["common_utilities", "is_furnished", "has_yard", "has_parking"]:
                field.widget.attrs.update({"class": "form-control"})

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "End date must be on or after the start date.")

        for field_name in self.DEFAULTED_FIELDS:
            if cleaned_data.get(field_name) in (None, ""):
                cleaned_data[field_name] = Listing._meta.get_field(field_name).get_default()

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        selected = self.cleaned_data.get("common_utilities", [])
        other = self.cleaned_data.get("other_utilities", "")

        all_utils = ", ".join(selected)
        if other:
            all_utils = f"{all_utils} | {other}" if all_utils else other

        instance.utilities_included = all_utils
        if commit:
            instance.save()

        return instance
