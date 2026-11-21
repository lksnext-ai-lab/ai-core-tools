"""Normalisation of uploaded pictures (user avatars, App images).

Uploads are decoded with Pillow, center-cropped to a square, resized to ``IMAGE_SIZE`` and re-encoded as
WebP: only that normalised image is ever stored, never the uploaded bytes (no EXIF/GPS metadata, no
polyglot files, bounded size).
"""
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
# Decoded-size cap checked before the pixels are loaded (a small file can expand to gigabytes).
MAX_SOURCE_PIXELS = 40_000_000
IMAGE_SIZE = 256
IMAGE_CONTENT_TYPE = "image/webp"
ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "WEBP", "GIF"})


class ImageValidationError(Exception):
    """The upload is not an acceptable picture. ``code`` is stable for the API."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def normalize_square_image(data: bytes) -> bytes:
    """Validate an uploaded picture and return it as a square ``IMAGE_SIZE`` WebP. CPU-bound."""
    if not data:
        raise ImageValidationError("IMAGE_EMPTY", "The file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageValidationError("IMAGE_TOO_LARGE", "The picture must be 5 MB or smaller.")

    try:
        with Image.open(BytesIO(data)) as source:
            if source.format not in ALLOWED_FORMATS:
                raise ImageValidationError("IMAGE_INVALID_TYPE", "Use a PNG, JPEG, WebP or GIF picture.")
            width, height = source.size
            if width < 1 or height < 1 or width * height > MAX_SOURCE_PIXELS:
                raise ImageValidationError("IMAGE_INVALID_DIMENSIONS", "The picture dimensions are not supported.")
            image = ImageOps.exif_transpose(source)  # first frame for animated images
            image = image.convert("RGBA" if _has_alpha(image) else "RGB")
            image = ImageOps.fit(image, (IMAGE_SIZE, IMAGE_SIZE), method=Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format="WEBP", quality=85, method=4)
            return output.getvalue()
    except ImageValidationError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError, SyntaxError) as exc:
        raise ImageValidationError("IMAGE_INVALID_IMAGE", "The file is not a readable picture.") from exc


def _has_alpha(image: Image.Image) -> bool:
    return image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info)
