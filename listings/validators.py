from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

ALLOWED_LISTING_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
ALLOWED_LISTING_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


def validate_listing_image(upload):
    extension = Path(upload.name).suffix.lower().lstrip(".")
    if extension not in ALLOWED_LISTING_IMAGE_EXTENSIONS:
        raise ValidationError("Upload a JPG, PNG, or WebP image.")

    content_type = getattr(upload, "content_type", "")
    if content_type and content_type not in ALLOWED_LISTING_IMAGE_CONTENT_TYPES:
        raise ValidationError("Unsupported image format.")

    if upload.size > settings.LISTING_IMAGE_MAX_BYTES:
        raise ValidationError("Each image must be 5 MB or smaller.")

    current_position = upload.tell() if hasattr(upload, "tell") else None
    try:
        with Image.open(upload) as image:
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError("Upload a valid image file.") from exc
    finally:
        if hasattr(upload, "seek") and current_position is not None:
            upload.seek(current_position)
