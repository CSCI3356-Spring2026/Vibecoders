from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError

ALLOWED_USER_FILE_EXTENSIONS = {
    "doc",
    "docx",
    "jpeg",
    "jpg",
    "pdf",
    "png",
    "txt",
    "webp",
}
ALLOWED_USER_FILE_CONTENT_TYPES = {
    "application/msword",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/jpeg",
    "image/png",
    "image/webp",
    "text/plain",
}


def validate_user_upload(upload):
    extension = Path(upload.name).suffix.lower().lstrip(".")
    if extension not in ALLOWED_USER_FILE_EXTENSIONS:
        raise ValidationError("Upload a PDF, image, text file, DOC, or DOCX file.")

    content_type = getattr(upload, "content_type", "")
    if content_type and content_type not in ALLOWED_USER_FILE_CONTENT_TYPES:
        raise ValidationError("Unsupported file type.")

    if upload.size > settings.USER_FILE_MAX_BYTES:
        raise ValidationError("Files must be 10 MB or smaller.")
