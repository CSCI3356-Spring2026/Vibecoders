from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from .geocoding import geocode_listing_address
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


def _original_listing_address(listing):
    if not listing.pk:
        return None
    return type(listing).objects.filter(pk=listing.pk).values_list("address", flat=True).first()


def sync_listing_coordinates(listing, *, previous_address=None):
    current_address = (listing.address or "").strip()
    if not current_address:
        listing.latitude = None
        listing.longitude = None
        return

    normalized_previous_address = (previous_address or "").strip() if previous_address is not None else None
    address_changed = normalized_previous_address is not None and current_address != normalized_previous_address
    coordinates_missing = listing.latitude is None or listing.longitude is None

    if not address_changed and not coordinates_missing:
        return

    if address_changed:
        listing.latitude = None
        listing.longitude = None

    latitude, longitude = geocode_listing_address(current_address)
    if latitude is not None and longitude is not None:
        listing.latitude = latitude
        listing.longitude = longitude


def save_listing_form(form, owner, uploaded_images):
    previous_address = _original_listing_address(form.instance)
    listing = form.save(commit=False)
    if listing._state.adding:
        listing.owner = owner
    sync_listing_coordinates(listing, previous_address=previous_address)

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
