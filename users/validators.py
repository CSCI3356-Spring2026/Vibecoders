from io import UnsupportedOperation
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from django.conf import settings
from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

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

DOC_FILE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
PDF_FILE_SIGNATURE = b"%PDF-"
DOCX_REQUIRED_MEMBERS = {"[Content_Types].xml", "word/document.xml"}
IMAGE_FILE_EXTENSIONS = {"jpeg", "jpg", "png", "webp"}


def _configured_upload_size_label(max_bytes):
    size_in_mb = max_bytes / (1024 * 1024)
    if size_in_mb.is_integer():
        return f"{int(size_in_mb)} MB"
    return f"{size_in_mb:.1f} MB"


def _inspect_upload(upload, inspector):
    try:
        current_position = upload.tell()
    except (AttributeError, OSError, UnsupportedOperation):
        current_position = None

    try:
        if hasattr(upload, "seek"):
            upload.seek(0)
        return inspector(upload)
    finally:
        if hasattr(upload, "seek") and current_position is not None:
            upload.seek(current_position)


def _validate_image_upload(upload):
    def inspector(file_obj):
        with Image.open(file_obj) as image:
            image.verify()

    try:
        _inspect_upload(upload, inspector)
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError("Upload a valid image file.") from exc


def _validate_pdf_upload(upload):
    def inspector(file_obj):
        return file_obj.read(len(PDF_FILE_SIGNATURE))

    if _inspect_upload(upload, inspector) != PDF_FILE_SIGNATURE:
        raise ValidationError("Upload a valid PDF file.")


def _validate_doc_upload(upload):
    def inspector(file_obj):
        return file_obj.read(len(DOC_FILE_SIGNATURE))

    if _inspect_upload(upload, inspector) != DOC_FILE_SIGNATURE:
        raise ValidationError("Upload a valid DOC file.")


def _validate_docx_upload(upload):
    def inspector(file_obj):
        with ZipFile(file_obj) as archive:
            return set(archive.namelist())

    try:
        members = _inspect_upload(upload, inspector)
    except (BadZipFile, OSError, ValueError) as exc:
        raise ValidationError("Upload a valid DOCX file.") from exc

    if not DOCX_REQUIRED_MEMBERS.issubset(members):
        raise ValidationError("Upload a valid DOCX file.")


def _validate_upload_contents(upload, extension):
    if extension in IMAGE_FILE_EXTENSIONS:
        _validate_image_upload(upload)
    elif extension == "pdf":
        _validate_pdf_upload(upload)
    elif extension == "doc":
        _validate_doc_upload(upload)
    elif extension == "docx":
        _validate_docx_upload(upload)


def validate_user_upload(upload):
    extension = Path(upload.name).suffix.lower().lstrip(".")
    if extension not in ALLOWED_USER_FILE_EXTENSIONS:
        raise ValidationError("Upload a PDF, image, text file, DOC, or DOCX file.")

    content_type = getattr(upload, "content_type", "")
    if content_type and content_type not in ALLOWED_USER_FILE_CONTENT_TYPES:
        raise ValidationError("Unsupported file type.")

    _validate_upload_contents(upload, extension)

    if upload.size > settings.USER_FILE_MAX_BYTES:
        raise ValidationError(
            f"Files must be {_configured_upload_size_label(settings.USER_FILE_MAX_BYTES)} or smaller."
        )
