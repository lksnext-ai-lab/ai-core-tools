"""User profile pictures.

Uploads are decoded with Pillow, center-cropped to a square, resized to ``AVATAR_SIZE`` and
re-encoded as WebP: only that normalised image is stored, never the uploaded bytes (no EXIF/GPS
metadata, no polyglot files, bounded size).
"""
from datetime import datetime
from io import BytesIO

from models.user_avatar import UserAvatar
from PIL import Image, ImageOps, UnidentifiedImageError
from repositories.user_avatar_repository import UserAvatarRepository
from sqlalchemy.orm import Session

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
# Decoded-size cap checked before the pixels are loaded (a small file can expand to gigabytes).
MAX_SOURCE_PIXELS = 40_000_000
AVATAR_SIZE = 256
AVATAR_CONTENT_TYPE = "image/webp"
ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "WEBP", "GIF"})


class AvatarValidationError(Exception):
    """The upload is not an acceptable picture. ``code`` is stable for the API."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def normalize_avatar_image(data: bytes) -> bytes:
    """Validate an uploaded picture and return it as a square ``AVATAR_SIZE`` WebP. CPU-bound."""
    if not data:
        raise AvatarValidationError("AVATAR_EMPTY", "The file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise AvatarValidationError("AVATAR_TOO_LARGE", "The picture must be 5 MB or smaller.")

    try:
        with Image.open(BytesIO(data)) as source:
            if source.format not in ALLOWED_FORMATS:
                raise AvatarValidationError("AVATAR_INVALID_TYPE", "Use a PNG, JPEG, WebP or GIF picture.")
            width, height = source.size
            if width < 1 or height < 1 or width * height > MAX_SOURCE_PIXELS:
                raise AvatarValidationError("AVATAR_INVALID_DIMENSIONS", "The picture dimensions are not supported.")
            image = ImageOps.exif_transpose(source)  # first frame for animated images
            image = image.convert("RGBA" if _has_alpha(image) else "RGB")
            image = ImageOps.fit(image, (AVATAR_SIZE, AVATAR_SIZE), method=Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format="WEBP", quality=85, method=4)
            return output.getvalue()
    except AvatarValidationError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError, SyntaxError) as exc:
        raise AvatarValidationError("AVATAR_INVALID_IMAGE", "The file is not a readable picture.") from exc


def _has_alpha(image: Image.Image) -> bool:
    return image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info)


class UserAvatarService:

    def __init__(self, db: Session):
        self.db = db
        self.repository = UserAvatarRepository(db)

    def get(self, user_id: int) -> UserAvatar | None:
        return self.repository.get(user_id)

    def get_updated_at(self, user_id: int) -> datetime | None:
        return self.repository.get_updated_at(user_id)

    def save(self, user_id: int, normalized_image: bytes) -> UserAvatar:
        """Store an image already produced by ``normalize_avatar_image``."""
        avatar = self.repository.upsert(user_id, normalized_image, AVATAR_CONTENT_TYPE)
        self.db.commit()
        return avatar

    def delete(self, user_id: int) -> bool:
        deleted = self.repository.delete(user_id)
        self.db.commit()
        return deleted
