from decimal import Decimal, InvalidOperation

from django import forms
from django.core import signing
from django.core.exceptions import ValidationError

from .address_provider import get_geoapify_autocomplete_config
from .address_signing import unsign_address_selection
from .fields import ListingImageField
from .group_matching import SLEEP_SCHEDULES
from .models import Listing, ListingImage

ADDRESS_SELECTION_MAX_AGE_SECONDS = 300


class ListingForm(forms.ModelForm):
    DEFAULTED_FIELDS = ("rooms", "bathrooms", "property_type", "lease_type", "status")
    UTILITY_CHOICES = [
        ("Water", "Water"),
        ("Gas", "Gas"),
        ("WiFi", "WiFi"),
        ("Electricity", "Electricity"),
        ("Trash", "Trash"),
    ]
    KNOWN_UTILITY_VALUES = {value for value, _ in UTILITY_CHOICES}
    OPTIONAL_DECIMAL_FIELDS = (
        "utilities_estimate",
        "parking_fee",
        "security_deposit",
        "application_fee",
        "distance_to_campus",
    )

    common_utilities = forms.MultipleChoiceField(
        choices=UTILITY_CHOICES,
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label="Included utilities",
    )
    other_utilities = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Heat, internet, laundry"}),
        label="Other utilities",
    )
    images = ListingImageField(required=False)
    verified_address_token = forms.CharField(required=False, widget=forms.HiddenInput())
    remove_images = forms.ModelMultipleChoiceField(
        queryset=ListingImage.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(),
        label="Remove current photos",
    )

    class Meta:
        model = Listing
        fields = [
            "title",
            "address",
            "property_type",
            "lease_type",
            "status",
            "is_hidden",
            "price",
            "utilities_estimate",
            "parking_fee",
            "security_deposit",
            "application_fee",
            "start_date",
            "end_date",
            "rooms",
            "bathrooms",
            "sq_ft",
            "distance_to_campus",
            "description",
            "pet_policy",
            "amenities",
            "security_features",
            "has_yard",
            "has_parking",
            "is_furnished",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "2-bed near Lower Campus"}),
            "address": forms.TextInput(attrs={"placeholder": "140 Commonwealth Ave"}),
            "price": forms.NumberInput(attrs={"step": "0.01", "min": "0", "placeholder": "1800"}),
            "utilities_estimate": forms.NumberInput(attrs={"step": "0.01", "min": "0", "placeholder": "120"}),
            "parking_fee": forms.NumberInput(attrs={"step": "0.01", "min": "0", "placeholder": "150"}),
            "security_deposit": forms.NumberInput(attrs={"step": "0.01", "min": "0", "placeholder": "1800"}),
            "application_fee": forms.NumberInput(attrs={"step": "0.01", "min": "0", "placeholder": "50"}),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "bathrooms": forms.NumberInput(attrs={"step": "0.5", "min": "0.5", "placeholder": "1.5"}),
            "sq_ft": forms.NumberInput(attrs={"min": "0", "placeholder": "950"}),
            "distance_to_campus": forms.NumberInput(attrs={"step": "0.1", "min": "0", "placeholder": "1.2"}),
            "description": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": "What renters should know.",
                }
            ),
            "pet_policy": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "No pets, or cats with approval.",
                }
            ),
            "amenities": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Dishwasher, in-unit laundry, central air.",
                }
            ),
            "security_features": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Secure entry, intercom, exterior lighting.",
                }
            ),
            "has_yard": forms.CheckboxInput(),
            "has_parking": forms.CheckboxInput(),
            "is_furnished": forms.CheckboxInput(),
            "is_hidden": forms.CheckboxInput(),
        }
        labels = {
            "property_type": "Home type",
            "lease_type": "Lease",
            "status": "Status",
            "is_hidden": "Hide from search",
            "price": "Rent / month",
            "utilities_estimate": "Utilities / month",
            "parking_fee": "Parking / month",
            "security_deposit": "Security deposit",
            "application_fee": "Application fee",
            "distance_to_campus": "Distance to campus (mi)",
            "sq_ft": "Square feet",
            "pet_policy": "Pet policy",
            "amenities": "Amenities",
            "security_features": "Security features",
            "rooms": "Bedrooms",
            "bathrooms": "Bathrooms",
        }
        help_texts = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["images"].widget.attrs.update({"accept": ".jpg,.jpeg,.png,.webp,image/*", "class": "form-control"})
        self.fields["address"].widget.attrs.update({"autocomplete": "off", "data-address-input": ""})
        self.fields["verified_address_token"].widget.attrs.update({"data-address-token-input": ""})
        if not get_geoapify_autocomplete_config()["enabled"]:
            self.fields["address"].widget.attrs.update({"readonly": "readonly", "aria-disabled": "true"})

        for field in self.fields.values():
            field.help_text = ""

        for field_name in self.DEFAULTED_FIELDS:
            self.fields[field_name].required = False
            if not self.is_bound:
                self.fields[field_name].initial = getattr(
                    self.instance, field_name, Listing._meta.get_field(field_name).get_default()
                )

        self.fields["description"].required = True

        if self.instance.pk:
            common_utilities, other_utilities = self._split_utilities(self.instance.utilities_included)
            self.fields["common_utilities"].initial = common_utilities
            self.fields["other_utilities"].initial = other_utilities
            self.fields["remove_images"].queryset = self.instance.images.all()
        else:
            self.fields["remove_images"].widget = forms.MultipleHiddenInput()

        for field_name, field in self.fields.items():
            if isinstance(field.widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple, forms.MultipleHiddenInput)):
                continue
            css_class = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{css_class} form-control".strip()

    @classmethod
    def _split_utilities(cls, value):
        if not value:
            return [], ""

        common = []
        other = []
        items = []
        for segment in value.split("|"):
            for item in segment.split(","):
                normalized = item.strip()
                if normalized:
                    items.append(normalized)

        for item in items:
            if item in cls.KNOWN_UTILITY_VALUES:
                common.append(item)
            else:
                other.append(item)

        return common, ", ".join(other)

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        self._clean_verified_address(cleaned_data)

        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "End date must be on or after the start date.")

        for field_name in self.DEFAULTED_FIELDS:
            if cleaned_data.get(field_name) in (None, ""):
                cleaned_data[field_name] = Listing._meta.get_field(field_name).get_default()

        for field_name in self.OPTIONAL_DECIMAL_FIELDS:
            value = cleaned_data.get(field_name)
            if value is not None and value < 0:
                self.add_error(field_name, "Enter a value greater than or equal to 0.")

        if not cleaned_data.get("description"):
            self.add_error("description", "Add a short description so renters understand the space.")

        self._clean_resulting_photo_count(cleaned_data)

        return cleaned_data

    def _clean_resulting_photo_count(self, cleaned_data):
        if self._resulting_photo_count(cleaned_data=cleaned_data) == 0:
            self.add_error("images", "Add at least one photo.")

    def _resulting_photo_count(self, *, cleaned_data=None):
        if cleaned_data is not None:
            uploaded_images = cleaned_data.get("images") or []
            removed_images_count = len(cleaned_data.get("remove_images") or [])
        else:
            uploaded_images = []
            removed_images_count = len(self.data.getlist(self.add_prefix("remove_images"))) if self.is_bound else 0

        existing_images_count = self.instance.images.count() if self.instance.pk else 0
        return max(existing_images_count - removed_images_count, 0) + len(uploaded_images)

    def _clean_verified_address(self, cleaned_data):
        if self._is_unchanged_instance_address(cleaned_data):
            cleaned_data["trusted_address_selection"] = {
                "address": self.instance.address,
                "latitude": self.instance.latitude,
                "longitude": self.instance.longitude,
            }
            return

        config = get_geoapify_autocomplete_config()
        if not config["enabled"]:
            self.add_error("address", "Verified address lookup is unavailable right now. Try again later.")
            return

        token = (cleaned_data.get("verified_address_token") or "").strip()
        if not token:
            self.add_error("address", "Select a verified address suggestion.")
            return

        try:
            trusted_selection = unsign_address_selection(token, max_age=ADDRESS_SELECTION_MAX_AGE_SECONDS)
        except signing.SignatureExpired:
            self.add_error("address", "Select a verified address suggestion.")
            return
        except signing.BadSignature:
            self.add_error("address", "Select a verified address suggestion.")
            return

        visible_address = (cleaned_data.get("address") or "").strip()
        trusted_address = (trusted_selection.get("label") or "").strip()
        if visible_address != trusted_address:
            self.add_error("address", "Choose the updated address from the verified suggestions.")
            return

        cleaned_data["trusted_address_selection"] = {
            "address": trusted_address,
            "latitude": trusted_selection.get("latitude"),
            "longitude": trusted_selection.get("longitude"),
        }

    def _is_unchanged_instance_address(self, cleaned_data):
        if not self.instance.pk:
            return False
        if self.instance.latitude is None or self.instance.longitude is None:
            return False

        visible_address = (cleaned_data.get("address") or "").strip()
        return bool(visible_address) and visible_address == (self.instance.address or "").strip()

    def save(self, commit=True):
        instance = super().save(commit=False)
        selected = self.cleaned_data.get("common_utilities", [])
        other = self.cleaned_data.get("other_utilities", "")

        other_items = [item.strip() for item in other.split(",") if item.strip()]
        instance.utilities_included = ", ".join([*selected, *other_items])

        if commit:
            instance.save()

        return instance

    def preview_value(self, field_name):
        field = self.fields[field_name]
        prefixed_name = self.add_prefix(field_name)

        if self.is_bound:
            if isinstance(field.widget, forms.CheckboxInput):
                return prefixed_name in self.data
            return self.data.get(prefixed_name) or None

        if self.instance.pk:
            value = getattr(self.instance, field_name)
            if value not in (None, ""):
                return value

        if field.initial not in (None, ""):
            return field.initial

        return None

    def preview_choice_label(self, field_name):
        value = self.preview_value(field_name)
        if value in (None, ""):
            return None

        choices = dict(self.fields[field_name].choices)
        return choices.get(value, value)

    def build_summary(self):
        def as_decimal(value):
            if value in (None, ""):
                return None
            if isinstance(value, Decimal):
                return value
            try:
                return Decimal(str(value))
            except (InvalidOperation, TypeError, ValueError):
                return None

        price = as_decimal(self.preview_value("price"))
        utilities = as_decimal(self.preview_value("utilities_estimate"))
        parking = as_decimal(self.preview_value("parking_fee"))
        deposit = as_decimal(self.preview_value("security_deposit"))
        application_fee = as_decimal(self.preview_value("application_fee"))
        monthly_total = (price or Decimal("0")) + (utilities or Decimal("0")) + (parking or Decimal("0"))
        upfront_total = (price or Decimal("0")) + (deposit or Decimal("0")) + (application_fee or Decimal("0"))
        bound_cleaned_data = self.cleaned_data if self.is_bound and hasattr(self, "cleaned_data") else None
        photo_count = self._resulting_photo_count(cleaned_data=bound_cleaned_data)

        checklist = [
            ("Basics", bool(self.preview_value("title") and self.preview_value("address"))),
            ("Dates", bool(self.preview_value("start_date") and self.preview_value("end_date"))),
            ("Pricing", bool(price)),
            (
                "Details",
                bool(
                    self.preview_value("property_type")
                    and self.preview_value("rooms")
                    and self.preview_value("bathrooms")
                ),
            ),
            ("Photos", bool(photo_count)),
        ]
        completed_sections = sum(1 for _, complete in checklist if complete)

        return {
            "title": self.preview_value("title") or "New listing",
            "address": self.preview_value("address") or "Add address",
            "property_type": self.preview_choice_label("property_type") or "Home",
            "lease_type": self.preview_choice_label("lease_type") or "Lease",
            "status": self.preview_choice_label("status") or "Available",
            "is_hidden": bool(self.preview_value("is_hidden")),
            "price": price,
            "utilities_estimate": utilities,
            "parking_fee": parking,
            "security_deposit": deposit,
            "application_fee": application_fee,
            "monthly_total": monthly_total if price is not None else None,
            "upfront_total": upfront_total if price is not None else None,
            "start_date": self.preview_value("start_date"),
            "end_date": self.preview_value("end_date"),
            "rooms": self.preview_value("rooms") or 1,
            "bathrooms": self.preview_value("bathrooms") or 1,
            "sq_ft": self.preview_value("sq_ft"),
            "photo_count": photo_count,
            "checklist": checklist,
            "completed_sections": completed_sections,
            "total_sections": len(checklist),
        }


class GroupMatchPreferencesForm(forms.Form):
    CLEANLINESS_CHOICES = [(value, f"{value}/5") for value in range(1, 6)]
    SOCIAL_CHOICES = [(value, f"{value}/5") for value in range(1, 6)]

    unit_size = forms.IntegerField(
        min_value=1,
        max_value=4,
        label="Your unit size",
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 4}),
    )
    budget_min = forms.DecimalField(
        min_value=0,
        max_digits=8,
        decimal_places=0,
        label="Budget min (per person)",
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": 50}),
    )
    budget_max = forms.DecimalField(
        min_value=0,
        max_digits=8,
        decimal_places=0,
        label="Budget max (per person)",
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": 50}),
    )
    cleanliness = forms.ChoiceField(
        choices=CLEANLINESS_CHOICES,
        label="Cleanliness level",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    social = forms.ChoiceField(
        choices=SOCIAL_CHOICES,
        label="Social level",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    sleep_schedule = forms.ChoiceField(
        choices=SLEEP_SCHEDULES,
        label="Sleep schedule",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    desired_group_min = forms.IntegerField(
        min_value=1,
        max_value=8,
        label="Desired group size (min)",
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 8}),
    )
    desired_group_max = forms.IntegerField(
        min_value=1,
        max_value=8,
        label="Desired group size (max)",
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 8}),
    )
    location_keywords = forms.CharField(
        required=False,
        label="Preferred areas",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Allston, Brighton, Chestnut Hill",
            }
        ),
    )

    def clean(self):
        cleaned_data = super().clean()
        budget_min = cleaned_data.get("budget_min")
        budget_max = cleaned_data.get("budget_max")
        desired_min = cleaned_data.get("desired_group_min")
        desired_max = cleaned_data.get("desired_group_max")

        if budget_min is not None and budget_max is not None and budget_min > budget_max:
            raise ValidationError("Budget min must be less than or equal to budget max.")
        if desired_min is not None and desired_max is not None and desired_min > desired_max:
            raise ValidationError("Desired group size min must be less than or equal to max.")

        return cleaned_data
