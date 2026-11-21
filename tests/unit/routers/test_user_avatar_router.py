"""Unit tests for the profile-picture endpoints in routers/internal/user.py (no DB)."""
from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from PIL import Image
from routers.internal import user as user_router

NOW = datetime(2026, 11, 21, 10, 0, tzinfo=UTC)


def _auth(email="ane@example.com"):
    return SimpleNamespace(identity=SimpleNamespace(email=email))


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


@pytest.fixture
def db_user(monkeypatch):
    user = SimpleNamespace(user_id=7, email="ane@example.com", name="Ane", platform_role="editor")
    monkeypatch.setattr(user_router.UserService, "get_user_by_email", lambda _db, _email: user)
    monkeypatch.setattr(user_router, "is_omniadmin", lambda _email: False)
    return user


@pytest.fixture
def avatar_service(monkeypatch):
    service = MagicMock()
    monkeypatch.setattr(user_router, "UserAvatarService", lambda _db: service)
    return service


async def test_me_returns_the_avatar_version(db_user, avatar_service):
    avatar_service.get_updated_at.return_value = NOW
    response = await user_router.get_current_user(_auth(), MagicMock())
    assert response.avatar_updated_at == NOW
    avatar_service.get_updated_at.assert_called_once_with(7)


async def test_get_avatar_returns_the_image(db_user, avatar_service):
    avatar_service.get.return_value = SimpleNamespace(content=b"img", content_type="image/webp")
    response = await user_router.get_my_avatar(_auth(), MagicMock())
    assert response.body == b"img"
    assert response.media_type == "image/webp"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-cache"


async def test_get_avatar_without_picture_is_404(db_user, avatar_service):
    avatar_service.get.return_value = None
    with pytest.raises(HTTPException) as exc:
        await user_router.get_my_avatar(_auth(), MagicMock())
    assert exc.value.status_code == 404


async def test_unknown_user_is_404(monkeypatch, avatar_service):
    monkeypatch.setattr(user_router.UserService, "get_user_by_email", lambda _db, _email: None)
    for call in (user_router.get_my_avatar, user_router.delete_my_avatar):
        with pytest.raises(HTTPException) as exc:
            await call(_auth(), MagicMock())
        assert exc.value.status_code == 404


async def test_upload_normalises_and_saves(db_user, avatar_service):
    avatar_service.save.return_value = SimpleNamespace(updated_at=NOW)
    upload = _Upload(_png())
    response = await user_router.upload_my_avatar(_auth(), MagicMock(), upload)
    assert response.avatar_updated_at == NOW
    assert upload.read_limit == user_router.MAX_UPLOAD_BYTES + 1
    user_id, stored = avatar_service.save.call_args.args
    assert user_id == 7
    with Image.open(BytesIO(stored)) as image:
        assert (image.format, image.size) == ("WEBP", (256, 256))


@pytest.mark.parametrize(
    ("data", "status_code", "code"),
    [
        (b"not an image", 400, "AVATAR_INVALID_IMAGE"),
        (b"\x00" * (user_router.MAX_UPLOAD_BYTES + 1), 413, "AVATAR_TOO_LARGE"),
    ],
)
async def test_invalid_upload_is_rejected_without_saving(db_user, avatar_service, data, status_code, code):
    with pytest.raises(HTTPException) as exc:
        await user_router.upload_my_avatar(_auth(), MagicMock(), _Upload(data))
    assert exc.value.status_code == status_code
    assert exc.value.detail["code"] == code
    avatar_service.save.assert_not_called()


async def test_delete_returns_204(db_user, avatar_service):
    response = await user_router.delete_my_avatar(_auth(), MagicMock())
    assert response.status_code == 204
    avatar_service.delete.assert_called_once_with(7)
