import mimetypes
from pathlib import PurePosixPath

from django.http import FileResponse, Http404


def normalize_public_media_subpath(path):
    normalized = PurePosixPath(str(path or "")).as_posix().strip()
    if not normalized or normalized.startswith("/"):
        raise Http404("File not found.")

    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise Http404("File not found.")

    return normalized


def public_file_response(file_field, *, cache_seconds=3600):
    try:
        file_handle = file_field.open("rb")
    except FileNotFoundError as exc:
        raise Http404("File not found.") from exc

    content_type = mimetypes.guess_type(file_field.name)[0] or "application/octet-stream"
    response = FileResponse(file_handle, content_type=content_type)
    response["Cache-Control"] = f"public, max-age={max(0, int(cache_seconds))}"
    response["X-Content-Type-Options"] = "nosniff"
    return response
