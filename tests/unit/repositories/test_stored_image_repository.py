"""Unit tests for StoredImageRepository against a mocked session (the real-DB path is in the integration tests)."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from models.app_image import AppImage
from models.user_avatar import UserAvatar
from repositories.stored_image_repository import StoredImageRepository

OWNERS = pytest.mark.parametrize(("model", "owner_column"), [(UserAvatar, "user_id"), (AppImage, "app_id")])


@OWNERS
def test_upsert_creates_a_row_when_missing(model, owner_column):
    db = MagicMock()
    db.get.return_value = None
    image = StoredImageRepository(db, model).upsert(5, b"img", "image/webp")
    db.add.assert_called_once_with(image)
    assert isinstance(image, model)
    assert (getattr(image, owner_column), image.content, image.content_type) == (5, b"img", "image/webp")
    assert image.updated_at is not None
    db.flush.assert_called_once()


@OWNERS
def test_upsert_updates_the_existing_row(model, owner_column):
    existing = model(**{owner_column: 5}, content=b"old", content_type="image/webp")
    db = MagicMock()
    db.get.return_value = existing
    image = StoredImageRepository(db, model).upsert(5, b"new", "image/webp")
    assert image is existing and image.content == b"new"
    db.add.assert_not_called()


@OWNERS
def test_get_and_get_updated_at(model, owner_column):
    db = MagicMock()
    db.get.return_value = "row"
    db.execute.return_value.scalar_one_or_none.return_value = "version"
    repo = StoredImageRepository(db, model)
    assert repo.get(5) == "row"
    db.get.assert_called_once_with(model, 5)
    assert repo.get_updated_at(5) == "version"


def test_get_versions_runs_one_query_and_skips_it_for_no_owners():
    db = MagicMock()
    db.execute.return_value.tuples.return_value.all.return_value = [(1, "v1"), (3, "v3")]
    repo = StoredImageRepository(db, AppImage)
    assert repo.get_versions(iter([1, 2, 3])) == {1: "v1", 3: "v3"}
    db.execute.assert_called_once()
    db.execute.reset_mock()
    assert repo.get_versions([]) == {}
    db.execute.assert_not_called()


def test_delete_reports_whether_a_row_was_removed():
    db = MagicMock()
    db.execute.return_value = SimpleNamespace(rowcount=1)
    assert StoredImageRepository(db, UserAvatar).delete(5) is True
    db.execute.return_value = SimpleNamespace(rowcount=0)
    assert StoredImageRepository(db, UserAvatar).delete(5) is False
