"""Unit tests for StoredImageService with a mocked repository (no DB)."""
from unittest.mock import MagicMock

import pytest
from models.app_image import AppImage
from models.user_avatar import UserAvatar
from services.stored_image_service import StoredImageService
from utils.image_normalization import IMAGE_CONTENT_TYPE


def _service(factory=StoredImageService.user_avatars):
    db = MagicMock()
    service = factory(db)
    service.repository = MagicMock()
    return service, db


@pytest.mark.parametrize(
    ("factory", "model"),
    [(StoredImageService.user_avatars, UserAvatar), (StoredImageService.app_images, AppImage)],
)
def test_factories_bind_the_owner_table(factory, model):
    assert factory(MagicMock()).repository.model is model


def test_save_stores_webp_and_commits():
    service, db = _service()
    service.repository.upsert.return_value = "image"
    assert service.save(3, b"img") == "image"
    service.repository.upsert.assert_called_once_with(3, b"img", IMAGE_CONTENT_TYPE)
    db.commit.assert_called_once()


def test_delete_commits_and_reports_whether_a_row_existed():
    service, db = _service()
    service.repository.delete.return_value = False
    assert service.delete(3) is False
    db.commit.assert_called_once()


def test_reads_are_delegated():
    service, _ = _service(StoredImageService.app_images)
    service.repository.get.return_value = "image"
    service.repository.get_updated_at.return_value = "version"
    service.repository.get_versions.return_value = {3: "version"}
    assert service.get(3) == "image"
    assert service.get_updated_at(3) == "version"
    assert service.get_versions([3]) == {3: "version"}
