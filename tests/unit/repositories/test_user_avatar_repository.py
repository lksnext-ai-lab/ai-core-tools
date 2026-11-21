"""Unit tests for UserAvatarRepository against a mocked session (the real-DB path is in the integration tests)."""
from types import SimpleNamespace
from unittest.mock import MagicMock

from models.user_avatar import UserAvatar
from repositories.user_avatar_repository import UserAvatarRepository


def test_upsert_creates_a_row_when_missing():
    db = MagicMock()
    db.get.return_value = None
    avatar = UserAvatarRepository(db).upsert(5, b"img", "image/webp")
    db.add.assert_called_once_with(avatar)
    assert isinstance(avatar, UserAvatar)
    assert (avatar.user_id, avatar.content, avatar.content_type) == (5, b"img", "image/webp")
    assert avatar.updated_at is not None
    db.flush.assert_called_once()


def test_upsert_updates_the_existing_row():
    existing = UserAvatar(user_id=5, content=b"old", content_type="image/webp")
    db = MagicMock()
    db.get.return_value = existing
    avatar = UserAvatarRepository(db).upsert(5, b"new", "image/webp")
    assert avatar is existing and avatar.content == b"new"
    db.add.assert_not_called()


def test_get_and_get_updated_at():
    db = MagicMock()
    db.get.return_value = "row"
    db.execute.return_value.scalar_one_or_none.return_value = "version"
    repo = UserAvatarRepository(db)
    assert repo.get(5) == "row"
    db.get.assert_called_once_with(UserAvatar, 5)
    assert repo.get_updated_at(5) == "version"


def test_delete_reports_whether_a_row_was_removed():
    db = MagicMock()
    db.execute.return_value = SimpleNamespace(rowcount=1)
    assert UserAvatarRepository(db).delete(5) is True
    db.execute.return_value = SimpleNamespace(rowcount=0)
    assert UserAvatarRepository(db).delete(5) is False
