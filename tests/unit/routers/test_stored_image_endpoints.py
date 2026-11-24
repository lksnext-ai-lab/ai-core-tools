"""Unit tests for the picture endpoints: the shared helpers, /me/avatar and /apps/{id}/image (no DB)."""
from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from PIL import Image
from routers.internal import app_images
from routers.internal import stored_image_endpoints as endpoints
from routers.internal import user as user_router
from utils.image_normalization import MAX_UPLOAD_BYTES

NOW = datetime(2026, 11, 21, 10, 0, tzinfo=UTC)


def _png() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (40, 20), (1, 2, 3)).save(buffer, format="PNG")
    return buffer.getvalue()


class _Upload:
    def __init__(self, data: bytes):
        self.data = data
        self.read_limit = None

    async def read(self, size=-1):
        self.read_limit = size
        return self.data


def _service(image=None):
    service = MagicMock()
    service.get.return_value = image
    service.save.return_value = SimpleNamespace(updated_at=NOW)
    return service


# --- shared helpers -------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("version", "cache_control"),
    [(None, endpoints.UNVERSIONED_CACHE_CONTROL), ("2026-11-21T10:00:00Z", endpoints.VERSIONED_CACHE_CONTROL)],
)
def test_image_response(version, cache_control):
    response = endpoints.image_response(
        _service(SimpleNamespace(content=b"img", content_type="image/webp")), 7, version)
    assert response.body == b"img"
    assert response.media_type == "image/webp"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == cache_control


def test_image_response_without_image_is_404():
    with pytest.raises(HTTPException) as exc:
        endpoints.image_response(_service(None), 7, None)
    assert exc.value.status_code == 404


async def test_store_uploaded_image_normalises_and_saves():
    service = _service()
    upload = _Upload(_png())
    assert await endpoints.store_uploaded_image(service, 7, upload) == NOW
    assert upload.read_limit == MAX_UPLOAD_BYTES + 1
    owner_id, stored = service.save.call_args.args
    assert owner_id == 7
    with Image.open(BytesIO(stored)) as image:
        assert (image.format, image.size) == ("WEBP", (256, 256))


@pytest.mark.parametrize(
    ("data", "status_code", "code"),
    [(b"not an image", 400, "IMAGE_INVALID_IMAGE"), (b"\x00" * (MAX_UPLOAD_BYTES + 1), 413, "IMAGE_TOO_LARGE")],
)
async def test_invalid_upload_is_rejected_without_saving(data, status_code, code):
    service = _service()
    with pytest.raises(HTTPException) as exc:
        await endpoints.store_uploaded_image(service, 7, _Upload(data))
    assert exc.value.status_code == status_code
    assert exc.value.detail["code"] == code
    service.save.assert_not_called()


def test_delete_image_returns_204():
    service = _service()
    assert endpoints.delete_image(service, 7).status_code == 204
    service.delete.assert_called_once_with(7)


# --- /me/avatar ------------------------------------------------------------------------------------------------


def _auth(email="ane@example.com"):
    return SimpleNamespace(identity=SimpleNamespace(email=email))


@pytest.fixture
def db_user(monkeypatch):
    user = SimpleNamespace(user_id=7, email="ane@example.com", name="Ane", platform_role="editor")
    monkeypatch.setattr(user_router.UserService, "get_user_by_email", lambda _db, _email: user)
    monkeypatch.setattr(user_router, "is_omniadmin", lambda _email: False)
    return user


@pytest.fixture
def avatars(monkeypatch):
    service = _service(SimpleNamespace(content=b"img", content_type="image/webp"))
    monkeypatch.setattr(user_router.StoredImageService, "user_avatars", lambda _db: service)
    return service


async def test_me_returns_the_avatar_version(db_user, avatars):
    avatars.get_updated_at.return_value = NOW
    response = await user_router.get_current_user(_auth(), MagicMock())
    assert response.avatar_updated_at == NOW
    avatars.get_updated_at.assert_called_once_with(7)


async def test_avatar_endpoints_act_on_the_current_user(db_user, avatars):
    assert (await user_router.get_my_avatar(_auth(), MagicMock(), v="x")).body == b"img"
    avatars.get.assert_called_once_with(7)
    response = await user_router.upload_my_avatar(_auth(), MagicMock(), _Upload(_png()))
    assert response.image_updated_at == NOW
    assert avatars.save.call_args.args[0] == 7
    assert (await user_router.delete_my_avatar(_auth(), MagicMock())).status_code == 204
    avatars.delete.assert_called_once_with(7)


async def test_unknown_user_is_404(monkeypatch, avatars):
    monkeypatch.setattr(user_router.UserService, "get_user_by_email", lambda _db, _email: None)
    for call in (user_router.get_my_avatar, user_router.delete_my_avatar):
        with pytest.raises(HTTPException) as exc:
            await call(_auth(), MagicMock())
        assert exc.value.status_code == 404


# --- /apps/{app_id}/image --------------------------------------------------------------------------------------


async def test_app_image_endpoints_act_on_the_app(monkeypatch):
    service = _service(SimpleNamespace(content=b"app", content_type="image/webp"))
    monkeypatch.setattr(app_images.StoredImageService, "app_images", lambda _db: service)
    assert (await app_images.get_app_image(3, MagicMock(), role=None)).body == b"app"
    service.get.assert_called_once_with(3)
    response = await app_images.upload_app_image(3, MagicMock(), role=None, file=_Upload(_png()))
    assert response.image_updated_at == NOW
    assert service.save.call_args.args[0] == 3
    assert (await app_images.delete_app_image(3, MagicMock(), role=None)).status_code == 204
    service.delete.assert_called_once_with(3)


@pytest.mark.parametrize(
    ("endpoint", "min_role"),
    [
        (app_images.get_app_image, "viewer"),
        (app_images.upload_app_image, "administrator"),
        (app_images.delete_app_image, "administrator"),
    ],
)
def test_app_image_endpoints_require_viewer_to_read_and_administrator_to_change(endpoint, min_role):
    import typing

    role_hint = typing.get_type_hints(endpoint, include_extras=True)["role"]
    checker = next(meta.dependency for meta in role_hint.__metadata__ if hasattr(meta, "dependency"))
    assert checker.required_min_role.value == min_role
