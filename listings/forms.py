from django import forms
from .models import Listing

class ListingForm(forms.ModelForm):
    # 1. Add the custom utility checkboxes
    UTILITY_CHOICES = [
        ('Water', 'Water'),
        ('Gas', 'Gas'),
        ('WiFi', 'WiFi'),
        ('Electricity', 'Electricity'),
        ('Trash', 'Trash'),
    ]
    common_utilities = forms.MultipleChoiceField(
        choices=UTILITY_CHOICES,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        required=False,
        label="Common Utilities"
    )
    other_utilities = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Other utilities...', 'class': 'form-control'}),
        label="Other"
    )

    images = forms.FileField(
        widget=forms.FileInput(), 
        required=False
    )

    class Meta:
        model = Listing
        exclude = ['owner', 'is_hidden', 'created_at', 'status', 'utilities_included'] # Hide original field
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            # 2. Set the step to 0.5 for bathrooms
            'bathrooms': forms.NumberInput(attrs={'step': '0.5', 'min': '0'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['images'].widget.attrs.update({'multiple': True})
        for field_name, field in self.fields.items():
            # Don't overwrite classes for our special logic fields
            if field_name not in ['common_utilities', 'is_furnished', 'has_yard', 'has_parking']:
                field.widget.attrs.update({'class': 'form-control'})

    # 3. Logic to merge checkboxes and 'other' into the database field
    def save(self, commit=True):
        instance = super().save(commit=False)
        selected = self.cleaned_data.get('common_utilities', [])
        other = self.cleaned_data.get('other_utilities', '')
        
        # Combine them: "Water, WiFi, Gas | Tenant pays for heat"
        all_utils = ", ".join(selected)
        if other:
            all_utils = f"{all_utils} | {other}" if all_utils else other
            
        instance.utilities_included = all_utils
        if commit:
            instance.save()
        return instance