from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import ValidationError
from django.utils import timezone

from .address_provider import get_geoapify_autocomplete_config
from .address_signing import unsign_address_selection
from .fields import ListingImageField
from .models import (
    Listing,
    ListingImage,
    ListingReport,
    ListingReview,
    RoommateGroup,
    RoommateGroupMembership,
    RoommatePost,
)

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


class RoommatePostForm(forms.ModelForm):
    TITLE_MIN_LENGTH = 5
    DESCRIPTION_MIN_LENGTH = 20

    class Meta:
        model = RoommatePost
        fields = [
            "title",
            "housing_status",
            "current_group_size",
            "open_spots",
            "budget_min",
            "budget_max",
            "move_in_date",
            "neighborhoods",
            "description",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Two BC seniors looking for one more roommate"}),
            "housing_status": forms.Select(attrs={"class": "form-select"}),
            "current_group_size": forms.NumberInput(attrs={"min": 1, "max": 8}),
            "open_spots": forms.NumberInput(attrs={"min": 1, "max": 8}),
            "budget_min": forms.NumberInput(attrs={"min": 0, "step": 50, "placeholder": "1200"}),
            "budget_max": forms.NumberInput(attrs={"min": 0, "step": 50, "placeholder": "1600"}),
            "move_in_date": forms.DateInput(attrs={"type": "date"}),
            "neighborhoods": forms.TextInput(attrs={"placeholder": "Allston, Brighton, Brookline"}),
            "description": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": (
                        "Who is already in the group, what kind of roommate fits best, "
                        "and what the housing plan looks like."
                    ),
                }
            ),
        }
        labels = {
            "title": "Post title",
            "housing_status": "Housing stage",
            "current_group_size": "People already in the group",
            "open_spots": "Open roommate spots",
            "budget_min": "Budget min / person",
            "budget_max": "Budget max / person",
            "move_in_date": "Target move-in",
            "neighborhoods": "Neighborhoods",
            "description": "What your group is looking for",
        }

    def __init__(self, *args, user=None, group=None, **kwargs):
        self.user = user
        self.group = group
        super().__init__(*args, **kwargs)

        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = "form-select"
            else:
                css_class = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = f"{css_class} form-control".strip()

        if not self.is_bound and not getattr(self.instance, "pk", None):
            self.fields["move_in_date"].initial = timezone.localdate() + timedelta(days=30)
        if self.group is not None:
            self.fields["current_group_size"].initial = self.group.member_count
            self.fields["current_group_size"].widget.attrs["readonly"] = "readonly"
            self.fields["current_group_size"].help_text = "Automatically set from your group members."

    def clean_title(self):
        title = (self.cleaned_data.get("title") or "").strip()
        if len(title) < self.TITLE_MIN_LENGTH:
            raise ValidationError("Make the title specific enough that people can understand the group.")
        return title

    def clean_description(self):
        description = (self.cleaned_data.get("description") or "").strip()
        if len(description) < self.DESCRIPTION_MIN_LENGTH:
            raise ValidationError("Add a short summary of who the group is and what you need.")
        if len(description) > 2000:
            raise ValidationError("Keep the post description to 2,000 characters or fewer.")
        return description

    def clean_neighborhoods(self):
        neighborhoods = (self.cleaned_data.get("neighborhoods") or "").strip()
        if not neighborhoods:
            return ""

        items = []
        for item in neighborhoods.split(","):
            normalized = item.strip()
            if normalized and normalized not in items:
                items.append(normalized)
        return ", ".join(items)

    def clean(self):
        cleaned_data = super().clean()
        user = self.user
        if user is not None and not getattr(user, "can_use_roommate_matching", False):
            raise ValidationError("Complete your roommate profile before posting for roommates.")
        if self.group is not None:
            cleaned_data["current_group_size"] = self.group.member_count
            self.instance.group = self.group
            self.instance.author = None
        elif self.user is not None:
            self.instance.author = self.user
            self.instance.group = None
        move_in_date = cleaned_data.get("move_in_date")
        if move_in_date and move_in_date < timezone.localdate():
            self.add_error("move_in_date", "Move-in date must be today or later.")
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.is_active = True
        if self.group is not None:
            instance.group = self.group
            instance.author = None
            instance.current_group_size = self.group.member_count
        elif self.user is not None and instance.author_id is None:
            instance.author = self.user
            instance.group = None
        if commit:
            instance.save()
        return instance


class RoommateGroupForm(forms.ModelForm):
    name = forms.CharField(
        max_length=RoommateGroup._meta.get_field("name").max_length,
        widget=forms.TextInput(attrs={"placeholder": "Beacon Street Housemates"}),
        label="Group name",
    )
    member_emails = forms.CharField(
        required=False,
        label="Member emails",
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "one@bc.edu, two@bc.edu",
            }
        ),
        help_text="Add active student emails separated by commas or new lines. Your email is included automatically.",
    )

    class Meta:
        model = RoommateGroup
        fields = ["name", "description"]
        widgets = {
            "description": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "A quick note about your group and living style.",
                }
            ),
        }
        labels = {
            "description": "Group summary",
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        self.member_users = []
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            css_class = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{css_class} form-control".strip()
        if self.instance.pk:
            member_emails = [
                member.email for member in self.instance.members.exclude(pk=self.instance.lead_id).order_by("email")
            ]
            self.fields["member_emails"].initial = ", ".join(member_emails)

    def _parse_member_emails(self):
        raw_value = self.cleaned_data.get("member_emails") or ""
        emails = []
        for item in raw_value.replace("\n", ",").split(","):
            normalized = item.strip().lower()
            if normalized and normalized not in emails:
                emails.append(normalized)
        return emails

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if len(name) < 3:
            raise ValidationError("Give the group a clearer name.")
        return name

    def clean_description(self):
        description = (self.cleaned_data.get("description") or "").strip()
        if len(description) > 500:
            raise ValidationError("Keep the group summary to 500 characters or fewer.")
        return description

    def clean(self):
        cleaned_data = super().clean()
        user = self.user
        if user is None or not getattr(user, "can_use_roommate_matching", False):
            raise ValidationError("Complete your roommate profile before creating a roommate group.")

        email_values = self._parse_member_emails()
        User = get_user_model()
        member_lookup = {
            member.email: member
            for member in User._default_manager.filter(
                email__in=email_values,
                role="student",
                is_active=True,
                profile_completed_at__isnull=False,
            )
        }
        missing_emails = [email for email in email_values if email not in member_lookup]
        if missing_emails:
            self.add_error("member_emails", f"These students are unavailable: {', '.join(missing_emails)}.")
        member_users = [user, *member_lookup.values()]
        deduped_members = []
        seen_ids = set()
        for member in member_users:
            if member.id not in seen_ids:
                deduped_members.append(member)
                seen_ids.add(member.id)
        if len(deduped_members) > 8:
            self.add_error("member_emails", "Keep roommate groups to 8 people or fewer.")
        self.member_users = deduped_members
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.user is not None and instance.lead_id is None:
            instance.lead = self.user
        if commit:
            instance.save()
            instance.memberships.exclude(user=instance.lead).delete()
            RoommateGroupMembership.objects.get_or_create(group=instance, user=instance.lead)
            current_member_ids = {instance.lead_id}
            for member in self.member_users:
                RoommateGroupMembership.objects.get_or_create(group=instance, user=member)
                current_member_ids.add(member.id)
            instance.memberships.exclude(user_id__in=current_member_ids).delete()
        return instance


class RoommatePostFilterForm(forms.Form):
    OPEN_SPOT_CHOICES = [
        ("", "Any open spots"),
        ("1", "1+ spot"),
        ("2", "2+ spots"),
        ("3", "3+ spots"),
    ]

    q = forms.CharField(
        required=False,
        label="Search",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Search neighborhoods, titles, majors",
            }
        ),
    )
    housing_status = forms.ChoiceField(
        required=False,
        label="Housing stage",
        choices=[("", "Any stage"), *RoommatePost.HOUSING_CHOICES],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    max_budget = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=8,
        decimal_places=0,
        label="Budget cap",
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": 50, "placeholder": "1600"}),
    )
    move_in_by = forms.DateField(
        required=False,
        label="Move in by",
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    open_spots_min = forms.ChoiceField(
        required=False,
        label="Open spots",
        choices=OPEN_SPOT_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def clean_open_spots_min(self):
        value = (self.cleaned_data.get("open_spots_min") or "").strip()
        if not value:
            return None
        return int(value)


STAR_RATING_CHOICES = [(value, "★" * value) for value in range(1, 6)]


class ListingReviewForm(forms.ModelForm):
    class Meta:
        model = ListingReview
        fields = ["rating", "comment"]
        widgets = {
            "rating": forms.RadioSelect(choices=STAR_RATING_CHOICES),
            "comment": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "What was the actual living experience like?",
                }
            ),
        }
        labels = {
            "rating": "Your rating",
            "comment": "Resident notes",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["comment"].required = False
        self.fields["rating"].widget.attrs.update({"class": "listing-review-stars"})
        self.fields["comment"].widget.attrs.update({"class": "form-control"})

    def clean_comment(self):
        comment = (self.cleaned_data.get("comment") or "").strip()
        if len(comment) > 2000:
            raise ValidationError("Keep comments to 2,000 characters or fewer.")
        return comment


class ListingReportForm(forms.ModelForm):
    class Meta:
        model = ListingReport
        fields = ["reason", "details"]
        widgets = {
            "reason": forms.Select(attrs={"class": "form-select"}),
            "details": forms.Textarea(
                attrs={
                    "rows": 4,
                    "class": "form-control",
                    "placeholder": "Tell the admin team what is wrong with this listing.",
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
        if reason == ListingReport.REASON_OTHER and not details:
            self.add_error("details", "Add context so the admin team can review this report.")
        if len(details) > 2000:
            self.add_error("details", "Keep report details to 2,000 characters or fewer.")
        cleaned_data["details"] = details
        return cleaned_data


class AdminListingApprovalForm(forms.Form):
    review_notes = forms.CharField(
        required=False,
        label="Review notes",
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "class": "form-control",
                "placeholder": "Internal review notes or feedback for the listing owner.",
            }
        ),
    )

    def clean_review_notes(self):
        notes = (self.cleaned_data.get("review_notes") or "").strip()
        if len(notes) > 2000:
            raise ValidationError("Keep review notes to 2,000 characters or fewer.")
        return notes


class AdminListingReportResolutionForm(forms.Form):
    status = forms.ChoiceField(
        choices=ListingReport.STATUS_CHOICES,
        label="Report status",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    resolution_notes = forms.CharField(
        required=False,
        label="Moderator note",
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "class": "form-control",
                "placeholder": "Explain the decision or add the next moderation step.",
            }
        ),
    )

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        initial = dict(kwargs.pop("initial", {}))
        if instance is not None:
            initial = {
                "status": instance.status,
                "resolution_notes": instance.resolution_notes,
                **initial,
            }
        kwargs["initial"] = initial
        super().__init__(*args, **kwargs)

    def clean_resolution_notes(self):
        notes = (self.cleaned_data.get("resolution_notes") or "").strip()
        if len(notes) > 2000:
            raise ValidationError("Keep resolution notes to 2,000 characters or fewer.")
        return notes

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get("status")
        notes = cleaned_data.get("resolution_notes") or ""
        if status in {ListingReport.STATUS_RESOLVED, ListingReport.STATUS_DISMISSED} and not notes:
            self.add_error("resolution_notes", "Add a moderator note before closing out a report.")
        cleaned_data["resolution_notes"] = notes
        return cleaned_data
