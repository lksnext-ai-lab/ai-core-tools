"""Integration tests for the App image: GET/PUT/DELETE /internal/apps/{app_id}/image and the App responses."""
from io import BytesIO

import pytest
from models.app_image import AppImage
from PIL import Image

pytestmark = pytest.mark.integration


def _png(size=(300, 120)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, (200, 120, 10)).save(buffer, format="PNG")
    return buffer.getvalue()


def _url(app):
    return f"/internal/apps/{app.app_id}/image"


def _upload(client, headers, app, data: bytes):
    return client.put(_url(app), headers=headers, files={"file": ("app.png", data, "image/png")})


def test_admin_uploads_and_every_member_sees_it(client, fake_app, app_admin_headers, app_viewer_headers):
    assert client.get(_url(fake_app), headers=app_viewer_headers).status_code == 404

    response = _upload(client, app_admin_headers, fake_app, _png())
    assert response.status_code == 200, response.text
    version = response.json()["image_updated_at"]

    picture = client.get(_url(fake_app), params={"v": version}, headers=app_viewer_headers)
    assert picture.status_code == 200
    assert picture.headers["content-type"] == "image/webp"
    assert "immutable" in picture.headers["cache-control"]
    with Image.open(BytesIO(picture.content)) as image:
        assert image.size == (256, 256)


def test_version_is_in_the_app_detail_and_list(client, fake_app, owner_headers):
    assert client.get(f"/internal/apps/{fake_app.app_id}", headers=owner_headers).json()["image_updated_at"] is None
    version = _upload(client, owner_headers, fake_app, _png()).json()["image_updated_at"]
    assert client.get(f"/internal/apps/{fake_app.app_id}", headers=owner_headers).json()["image_updated_at"] == version
    listed = {app["app_id"]: app for app in client.get("/internal/apps/", headers=owner_headers).json()}
    assert listed[fake_app.app_id]["image_updated_at"] == version


@pytest.mark.parametrize("headers_fixture", ["app_editor_headers", "app_viewer_headers"])
def test_below_administrator_cannot_change_it(client, fake_app, owner_headers, headers_fixture, request):
    _upload(client, owner_headers, fake_app, _png())
    headers = request.getfixturevalue(headers_fixture)
    assert _upload(client, headers, fake_app, _png()).status_code == 403
    assert client.delete(_url(fake_app), headers=headers).status_code == 403
    assert client.get(_url(fake_app), headers=headers).status_code == 200


def test_non_member_gets_403_and_missing_app_404(client, fake_app, owner_headers, auth_headers, db):
    from utils.local_auth_tokens import mint_access_token

    from tests.factories import UserFactory, configure_factories

    _upload(client, owner_headers, fake_app, _png())
    configure_factories(db)
    stranger = UserFactory()
    db.flush()
    token, _ = mint_access_token(stranger.user_id, stranger.email, stranger.name)
    assert client.get(_url(fake_app), headers={"Authorization": f"Bearer {token}"}).status_code == 403
    assert client.get("/internal/apps/999999/image", headers=owner_headers).status_code == 404


def test_invalid_upload_is_rejected_and_delete_removes_it(client, fake_app, owner_headers):
    _upload(client, owner_headers, fake_app, _png())
    response = _upload(client, owner_headers, fake_app, b"not an image")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "IMAGE_INVALID_IMAGE"
    assert client.get(_url(fake_app), headers=owner_headers).status_code == 200
    assert client.delete(_url(fake_app), headers=owner_headers).status_code == 204
    assert client.get(_url(fake_app), headers=owner_headers).status_code == 404


def test_image_is_deleted_with_the_app(client, fake_app, owner_headers, db):
    _upload(client, owner_headers, fake_app, _png())
    app_id = fake_app.app_id
    assert client.delete(f"/internal/apps/{app_id}", headers=owner_headers).status_code in (200, 204)
    db.expire_all()
    assert db.get(AppImage, app_id) is None
