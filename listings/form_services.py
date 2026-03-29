from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import ListingImage


def build_validated_listing_images(listing, uploaded_images, *, removed_images_count=0):
    if len(uploaded_images) > settings.LISTING_IMAGE_UPLOAD_LIMIT:
        raise ValidationError({"images": f"You can upload up to {settings.LISTING_IMAGE_UPLOAD_LIMIT} images."})

    existing_images_count = max(listing.images.count() - removed_images_count, 0)
    if existing_images_count + len(uploaded_images) > settings.LISTING_IMAGE_TOTAL_LIMIT:
        raise ValidationError(
            {"images": f"Each listing can have up to {settings.LISTING_IMAGE_TOTAL_LIMIT} images total."}
        )

    pending_images = []
    for image in uploaded_images:
        listing_image = ListingImage(listing=listing, image=image)
        listing_image.full_clean()
        pending_images.append(listing_image)

    return pending_images


def save_uploaded_listing_images(pending_images):
    for listing_image in pending_images:
        listing_image.save()


def add_form_validation_errors(form, exc):
    if hasattr(exc, "message_dict"):
        for field_name, messages_list in exc.message_dict.items():
            target_field = "images" if field_name == "image" else field_name
            for message in messages_list:
                form.add_error(target_field, message)
        return

    for message in exc.messages:
        form.add_error("images", message)


def validation_message(exc, default_message):
    if hasattr(exc, "message_dict"):
        for messages_list in exc.message_dict.values():
            if messages_list:
                return messages_list[0]
    if getattr(exc, "messages", None):
        return exc.messages[0]
    return default_message


def save_listing_form(form, owner, uploaded_images):
    listing = form.save(commit=False)
    if listing._state.adding:
        listing.owner = owner

    trusted_selection = form.cleaned_data["trusted_address_selection"]
    listing.address = trusted_selection["address"]
    listing.latitude = trusted_selection["latitude"]
    listing.longitude = trusted_selection["longitude"]
    listing.submit_for_approval()

    with transaction.atomic():
        listing.save()
        images_to_remove = list(form.cleaned_data.get("remove_images", []))
        pending_images = build_validated_listing_images(
            listing,
            uploaded_images,
            removed_images_count=len(images_to_remove),
        )
        for image in images_to_remove:
            image.delete()
        save_uploaded_listing_images(pending_images)
        return listing


def handle_listing_form_submission(*, form, owner):
    if form.is_valid():
        uploaded_images = form.cleaned_data.get("images", [])
        try:
            return save_listing_form(form, owner, uploaded_images)
        except ValidationError as exc:
            add_form_validation_errors(form, exc)
    return None
