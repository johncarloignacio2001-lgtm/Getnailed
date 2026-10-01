import uuid
import warnings
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError


ALLOWED_IMAGE_TYPES = {
    ".jpg": ("JPEG", "image/jpeg", ".jpg"),
    ".jpeg": ("JPEG", "image/jpeg", ".jpg"),
    ".png": ("PNG", "image/png", ".png"),
    ".webp": ("WEBP", "image/webp", ".webp"),
}


def validate_image_upload(uploaded_file):
    if uploaded_file.size > settings.MAX_IMAGE_UPLOAD_SIZE:
        max_megabytes = settings.MAX_IMAGE_UPLOAD_SIZE // (1024 * 1024)
        raise ValidationError(f"Image files must be {max_megabytes} MB or smaller.")

    extension = Path(uploaded_file.name).suffix.lower()
    expected = ALLOWED_IMAGE_TYPES.get(extension)
    if expected is None:
        raise ValidationError("Only JPEG, PNG, and WebP images are allowed.")

    expected_format, expected_content_type, _ = expected
    content_type = getattr(uploaded_file, "content_type", "") or getattr(
        getattr(uploaded_file, "file", None),
        "content_type",
        "",
    )
    if content_type != expected_content_type:
        raise ValidationError("The image type does not match its filename.")

    try:
        uploaded_file.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(uploaded_file) as image:
                actual_format = image.format
                width, height = image.size
                if width * height > settings.MAX_IMAGE_UPLOAD_PIXELS:
                    raise ValidationError("The image dimensions are too large.")
                image.verify()
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        UnidentifiedImageError,
        ValueError,
    ) as exc:
        raise ValidationError("Upload a valid, non-corrupted image.") from exc
    finally:
        uploaded_file.seek(0)

    if actual_format != expected_format:
        raise ValidationError("The image content does not match its filename.")


def safe_image_upload_path(instance, filename):
    extension = Path(filename).suffix.lower()
    allowed_type = ALLOWED_IMAGE_TYPES.get(extension)
    if allowed_type is None:
        raise ValidationError("Unsupported image filename extension.")
    canonical_extension = allowed_type[2]
    return f"service-images/{uuid.uuid4().hex}{canonical_extension}"
