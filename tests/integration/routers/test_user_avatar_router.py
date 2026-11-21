"""Integration tests for the profile-picture endpoints: PUT/GET/DELETE /internal/me/avatar and /internal/me."""
from io import BytesIO

import pytest
from models.user_avatar import UserAvatar
from PIL import Image
from utils.local_auth_tokens import mint_access_token

from tests.factories import UserFactory, configure_factories

pytestmark = pytest.mark.integration


def _png(size=(300, 120)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, (10, 120, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


def _upload(client, headers, data: bytes, filename="me.png", content_type="image/png"):
    return client.put("/internal/me/avatar", headers=headers, files={"file": (filename, data, content_type)})


def test_me_has_no_avatar_by_default(client, auth_headers):
    response = client.get("/internal/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["avatar_updated_at"] is None
    assert client.get("/internal/me/avatar", headers=auth_headers).status_code == 404


def test_upload_then_get_returns_the_normalised_picture(client, auth_headers):
    response = _upload(client, auth_headers, _png())
    assert response.status_code == 200, response.text
    updated_at = response.json()["image_updated_at"]
    assert updated_at

    me = client.get("/internal/me", headers=auth_headers).json()
    assert me["avatar_updated_at"] == updated_at

    picture = client.get("/internal/me/avatar", headers=auth_headers)
    assert picture.status_code == 200
    assert picture.headers["content-type"] == "image/webp"
    assert picture.headers["x-content-type-options"] == "nosniff"
    with Image.open(BytesIO(picture.content)) as image:
        assert image.size == (256, 256)


def test_upload_replaces_the_previous_picture(client, auth_headers, db, fake_user):
    first = _upload(client, auth_headers, _png()).json()["image_updated_at"]
    second = _upload(client, auth_headers, _png((50, 50))).json()["image_updated_at"]
    assert second >= first
    assert db.query(UserAvatar).filter(UserAvatar.user_id == fake_user.user_id).count() == 1


def test_invalid_upload_is_rejected_and_keeps_the_current_picture(client, auth_headers):
    _upload(client, auth_headers, _png())
    response = _upload(client, auth_headers, b"not an image", filename="x.png")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "IMAGE_INVALID_IMAGE"
    assert client.get("/internal/me/avatar", headers=auth_headers).status_code == 200


def test_too_large_upload_gets_413(client, auth_headers):
    response = _upload(client, auth_headers, b"\x00" * (5 * 1024 * 1024 + 10))
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "IMAGE_TOO_LARGE"


def test_delete_removes_the_picture_and_is_idempotent(client, auth_headers):
    _upload(client, auth_headers, _png())
    assert client.delete("/internal/me/avatar", headers=auth_headers).status_code == 204
    assert client.get("/internal/me/avatar", headers=auth_headers).status_code == 404
    assert client.get("/internal/me", headers=auth_headers).json()["avatar_updated_at"] is None
    assert client.delete("/internal/me/avatar", headers=auth_headers).status_code == 204


def test_each_user_only_sees_their_own_picture(client, auth_headers, db):
    _upload(client, auth_headers, _png())
    configure_factories(db)
    other = UserFactory()
    db.flush()
    token, _ = mint_access_token(other.user_id, other.email, other.name)
    other_headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/internal/me/avatar", headers=other_headers).status_code == 404


def test_endpoints_require_authentication(client):
    assert client.get("/internal/me/avatar").status_code == 401
    assert client.put("/internal/me/avatar", files={"file": ("a.png", _png(), "image/png")}).status_code in (401, 403)
    assert client.delete("/internal/me/avatar").status_code in (401, 403)


def test_picture_is_deleted_with_the_user(client, auth_headers, db, fake_user):
    _upload(client, auth_headers, _png())
    user_id = fake_user.user_id
    db.delete(fake_user)
    db.flush()
    db.expire_all()
    assert db.get(UserAvatar, user_id) is None
