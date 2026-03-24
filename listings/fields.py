from django import forms


class ListingImageInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class ListingImageField(forms.FileField):
    widget = ListingImageInput

    def clean(self, data, initial=None):
        single_file_clean = super().clean

        if not data:
            return []

        if isinstance(data, (list, tuple)):
            return [single_file_clean(item, None) for item in data]

        return [single_file_clean(data, initial)]
