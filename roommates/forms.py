from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import RoommateGroup, RoommatePost


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

        for field in self.fields.values():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = "form-select"
            else:
                css_class = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = f"{css_class} form-control".strip()

        self.fields["housing_status"].label = "Your housing stage"
        self.fields["housing_status"].help_text = (
            "Pick your situation. Roommates uses this to connect people who have a place "
            "with people who still need one."
        )

        if not self.is_bound and not getattr(self.instance, "pk", None):
            self.fields["move_in_date"].initial = timezone.localdate() + timedelta(days=30)
        if self.group is not None:
            self.fields["current_group_size"].initial = self.group.member_count
            self.fields["current_group_size"].widget.attrs["readonly"] = "readonly"
            self.fields["current_group_size"].help_text = "Automatically set from your group members."
        self.fields["open_spots"].required = False
        self.fields["open_spots"].help_text = "Required when you already have a place."

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
        if self.user is not None and not getattr(self.user, "can_use_roommate_matching", False):
            raise ValidationError("Complete your roommate profile before posting.")
        if self.group is not None:
            cleaned_data["current_group_size"] = self.group.member_count
            self.instance.group = self.group
            self.instance.author = None
        elif self.user is not None:
            self.instance.author = self.user
            self.instance.group = None

        move_in_date = cleaned_data.get("move_in_date")
        housing_status = cleaned_data.get("housing_status")
        open_spots = cleaned_data.get("open_spots")
        if housing_status == RoommatePost.HOUSING_HAVE_HOME and open_spots is None:
            self.add_error("open_spots", "Add how many open roommate spots you have.")
        if open_spots is not None and open_spots < 1:
            self.add_error("open_spots", "Open roommate spots must be at least 1.")
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
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css_class = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{css_class} form-control".strip()

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
        if self.user is None or not getattr(self.user, "can_use_roommate_matching", False):
            raise ValidationError("Complete your roommate profile before creating a group.")
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.user is not None and instance.lead_id is None:
            instance.lead = self.user
        if commit:
            instance.save()
        return instance


class RoommatePostFilterForm(forms.Form):
    HOUSING_FILTER_CHOICES = [
        ("", "Any stage"),
        (RoommatePost.HOUSING_HAVE_HOME, "Already have a place"),
        (RoommatePost.HOUSING_NEED_HOME, "Need a place"),
    ]
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
        choices=HOUSING_FILTER_CHOICES,
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
    people_in_group = forms.IntegerField(
        required=False,
        min_value=1,
        label="People in my group",
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 1, "placeholder": "2"}),
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
