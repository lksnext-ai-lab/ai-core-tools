"""Unit tests for the profile-picture normalisation (no DB)."""
from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image
from services.user_avatar_service import (
    AVATAR_SIZE,
    MAX_UPLOAD_BYTES,
    AvatarValidationError,
    normalize_avatar_image,
)


def _image_bytes(fmt: str, size=(400, 200), mode="RGB", color=(200, 30, 30), **save_kwargs) -> bytes:
    buffer = BytesIO()
    Image.new(mode, size, color).save(buffer, format=fmt, **save_kwargs)
    return buffer.getvalue()


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP", "GIF"])
def test_accepted_formats_become_a_square_webp(fmt):
    result = normalize_avatar_image(_image_bytes(fmt))
    with Image.open(BytesIO(result)) as image:
        assert image.format == "WEBP"
        assert image.size == (AVATAR_SIZE, AVATAR_SIZE)


def test_transparency_is_kept():
    result = normalize_avatar_image(_image_bytes("PNG", mode="RGBA", color=(0, 0, 0, 0)))
    with Image.open(BytesIO(result)) as image:
        assert image.mode == "RGBA"
        assert image.getpixel((10, 10))[3] == 0


def test_exif_metadata_is_dropped():
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: rotate 90 CW
    exif[0x010F] = "SecretCam"  # Make
    source = _image_bytes("JPEG", size=(300, 100), exif=exif.tobytes())
    result = normalize_avatar_image(source)
    with Image.open(BytesIO(result)) as image:
        assert not image.getexif()
    assert b"SecretCam" not in result


def test_empty_file_is_rejected():
    with pytest.raises(AvatarValidationError) as exc:
        normalize_avatar_image(b"")
    assert exc.value.code == "AVATAR_EMPTY"


def test_oversized_file_is_rejected_before_decoding():
    with pytest.raises(AvatarValidationError) as exc:
        normalize_avatar_image(b"\x00" * (MAX_UPLOAD_BYTES + 1))
    assert exc.value.code == "AVATAR_TOO_LARGE"


def test_non_image_is_rejected():
    with pytest.raises(AvatarValidationError) as exc:
        normalize_avatar_image(b"<svg xmlns='http://www.w3.org/2000/svg'></svg>")
    assert exc.value.code == "AVATAR_INVALID_IMAGE"


def test_unsupported_format_is_rejected():
    with pytest.raises(AvatarValidationError) as exc:
        normalize_avatar_image(_image_bytes("BMP"))
    assert exc.value.code == "AVATAR_INVALID_TYPE"


def test_truncated_image_is_rejected():
    data = _image_bytes("PNG", size=(500, 500))
    with pytest.raises(AvatarValidationError) as exc:
        normalize_avatar_image(data[: len(data) // 2])
    assert exc.value.code == "AVATAR_INVALID_IMAGE"


def test_huge_dimensions_are_rejected_without_decoding():
    # A tiny 1-bit PNG that decodes to 50M pixels.
    data = _image_bytes("PNG", size=(10_000, 5_000), mode="1", color=0)
    assert len(data) < MAX_UPLOAD_BYTES
    with pytest.raises(AvatarValidationError) as exc:
        normalize_avatar_image(data)
    assert exc.value.code == "AVATAR_INVALID_DIMENSIONS"


class TestUserAvatarService:
    def _service(self):
        from unittest.mock import MagicMock

        from services.user_avatar_service import UserAvatarService

        db = MagicMock()
        service = UserAvatarService(db)
        service.repository = MagicMock()
        return service, db

    def test_save_stores_webp_and_commits(self):
        from services.user_avatar_service import AVATAR_CONTENT_TYPE

        service, db = self._service()
        service.repository.upsert.return_value = "avatar"
        assert service.save(3, b"img") == "avatar"
        service.repository.upsert.assert_called_once_with(3, b"img", AVATAR_CONTENT_TYPE)
        db.commit.assert_called_once()

    def test_delete_commits_and_reports_whether_a_row_existed(self):
        service, db = self._service()
        service.repository.delete.return_value = False
        assert service.delete(3) is False
        db.commit.assert_called_once()

    def test_reads_are_delegated(self):
        service, _ = self._service()
        service.repository.get.return_value = "avatar"
        service.repository.get_updated_at.return_value = "version"
        assert service.get(3) == "avatar"
        assert service.get_updated_at(3) == "version"
