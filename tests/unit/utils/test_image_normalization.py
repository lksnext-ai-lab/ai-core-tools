"""Unit tests for the picture normalisation shared by user avatars and App images (no DB)."""
from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image
from utils.image_normalization import (
    IMAGE_SIZE,
    MAX_UPLOAD_BYTES,
    ImageValidationError,
    normalize_square_image,
)


def _image_bytes(fmt: str, size=(400, 200), mode="RGB", color=(200, 30, 30), **save_kwargs) -> bytes:
    buffer = BytesIO()
    Image.new(mode, size, color).save(buffer, format=fmt, **save_kwargs)
    return buffer.getvalue()


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP", "GIF"])
def test_accepted_formats_become_a_square_webp(fmt):
    result = normalize_square_image(_image_bytes(fmt))
    with Image.open(BytesIO(result)) as image:
        assert image.format == "WEBP"
        assert image.size == (IMAGE_SIZE, IMAGE_SIZE)


def test_transparency_is_kept():
    result = normalize_square_image(_image_bytes("PNG", mode="RGBA", color=(0, 0, 0, 0)))
    with Image.open(BytesIO(result)) as image:
        assert image.mode == "RGBA"
        assert image.getpixel((10, 10))[3] == 0


def test_exif_metadata_is_dropped():
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: rotate 90 CW
    exif[0x010F] = "SecretCam"  # Make
    source = _image_bytes("JPEG", size=(300, 100), exif=exif.tobytes())
    result = normalize_square_image(source)
    with Image.open(BytesIO(result)) as image:
        assert not image.getexif()
    assert b"SecretCam" not in result


def test_empty_file_is_rejected():
    with pytest.raises(ImageValidationError) as exc:
        normalize_square_image(b"")
    assert exc.value.code == "IMAGE_EMPTY"


def test_oversized_file_is_rejected_before_decoding():
    with pytest.raises(ImageValidationError) as exc:
        normalize_square_image(b"\x00" * (MAX_UPLOAD_BYTES + 1))
    assert exc.value.code == "IMAGE_TOO_LARGE"


def test_non_image_is_rejected():
    with pytest.raises(ImageValidationError) as exc:
        normalize_square_image(b"<svg xmlns='http://www.w3.org/2000/svg'></svg>")
    assert exc.value.code == "IMAGE_INVALID_IMAGE"


def test_unsupported_format_is_rejected():
    with pytest.raises(ImageValidationError) as exc:
        normalize_square_image(_image_bytes("BMP"))
    assert exc.value.code == "IMAGE_INVALID_TYPE"


def test_truncated_image_is_rejected():
    data = _image_bytes("PNG", size=(500, 500))
    with pytest.raises(ImageValidationError) as exc:
        normalize_square_image(data[: len(data) // 2])
    assert exc.value.code == "IMAGE_INVALID_IMAGE"


def test_huge_dimensions_are_rejected_without_decoding():
    # A tiny 1-bit PNG that decodes to 50M pixels.
    data = _image_bytes("PNG", size=(10_000, 5_000), mode="1", color=0)
    assert len(data) < MAX_UPLOAD_BYTES
    with pytest.raises(ImageValidationError) as exc:
        normalize_square_image(data)
    assert exc.value.code == "IMAGE_INVALID_DIMENSIONS"

