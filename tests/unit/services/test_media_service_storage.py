"""
Unit tests for the storage-related code paths in MediaService:

  - create_media_from_file  storage_key derivation, backend.upload call
  - delete_media            backend.delete for primary key + audio cleanup

The storage backend is replaced with a MagicMock whose upload / delete / exists
methods are AsyncMocks.  No real filesystem or S3 calls are made.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from services.media_service import MediaService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_upload_file(mocker, *, filename: str = "clip.mp4", content: bytes = b"video bytes"):
    """Minimal UploadFile mock."""
    f = mocker.MagicMock()
    f.filename = filename
    f.content_type = "video/mp4"
    f.read = mocker.AsyncMock(return_value=content)
    return f


def _make_media_orm(mocker, *, storage_key: str | None = "repositories/1/7.mp4", media_id: int = 7):
    """Minimal Media ORM-like mock."""
    m = mocker.MagicMock()
    m.media_id = media_id
    m.storage_key = storage_key
    return m


# ---------------------------------------------------------------------------
# create_media_from_file
# ---------------------------------------------------------------------------

class TestCreateMediaFromFile:
    """
    Storage-related behaviour of create_media_from_file:
      - key follows the pattern  repositories/{repository_id}/{media_id}{ext}
      - backend.upload is called exactly once with that key and the file bytes
      - media.storage_key is set to the key before returning
    """

    @pytest.fixture(autouse=True)
    def _patch_deps(self, mocker):
        # Replace storage backend
        self.mock_backend = mocker.MagicMock()
        self.mock_backend.upload = mocker.AsyncMock()
        mocker.patch(
            "services.media_service.get_storage_backend",
            return_value=self.mock_backend,
        )
        # Suppress the background media processing import
        mocker.patch.dict(
            "sys.modules",
            {"tasks": MagicMock(), "tasks.media_tasks": MagicMock()},
        )

    def _db_with_flush(self, mocker, *, media_id: int = 42):
        """Return a mock Session whose flush() assigns media_id to the last added object."""
        db = mocker.MagicMock()

        def _flush():
            last = db.add.call_args_list[-1].args[0]
            last.media_id = media_id

        db.flush.side_effect = _flush
        return db

    @pytest.mark.asyncio
    async def test_storage_key_matches_expected_pattern(self, mocker):
        db = self._db_with_flush(mocker, media_id=42)

        result = await MediaService.create_media_from_file(
            file=_make_upload_file(mocker, filename="clip.mp4"),
            repository_id=10,
            folder_id=None,
            db=db,
            background_tasks=mocker.MagicMock(),
        )

        assert result.storage_key == "repositories/10/42.mp4"

    @pytest.mark.asyncio
    async def test_backend_upload_called_once_with_key_and_content(self, mocker):
        content = b"real video bytes"
        db = self._db_with_flush(mocker, media_id=7)

        await MediaService.create_media_from_file(
            file=_make_upload_file(mocker, filename="clip.mp4", content=content),
            repository_id=5,
            folder_id=None,
            db=db,
            background_tasks=mocker.MagicMock(),
        )

        self.mock_backend.upload.assert_called_once_with(
            "repositories/5/7.mp4",
            content,
            content_type="video/mp4",
        )

    @pytest.mark.asyncio
    async def test_storage_key_preserves_original_file_extension(self, mocker):
        db = self._db_with_flush(mocker, media_id=3)

        result = await MediaService.create_media_from_file(
            file=_make_upload_file(mocker, filename="audio.wav"),
            repository_id=20,
            folder_id=None,
            db=db,
            background_tasks=mocker.MagicMock(),
        )

        assert result.storage_key.endswith(".wav")
        assert result.storage_key.startswith("repositories/20/")

    @pytest.mark.asyncio
    async def test_returned_media_storage_key_is_set(self, mocker):
        """The returned Media object carries the final storage_key."""
        db = self._db_with_flush(mocker, media_id=99)

        result = await MediaService.create_media_from_file(
            file=_make_upload_file(mocker, filename="video.mp4"),
            repository_id=1,
            folder_id=None,
            db=db,
            background_tasks=mocker.MagicMock(),
        )

        assert result.storage_key is not None
        assert result.storage_key != ""


# ---------------------------------------------------------------------------
# delete_media
# ---------------------------------------------------------------------------

class TestDeleteMedia:
    """
    Storage cleanup behaviour of delete_media:
      - backend.delete(storage_key) is called for the primary file
      - backend.delete is also called for the derived audio key when it exists
      - nothing is deleted when storage_key is None / empty
      - returns False when the Media record does not exist
    """

    @pytest.fixture(autouse=True)
    def _patch_deps(self, mocker):
        self.mock_backend = mocker.MagicMock()
        self.mock_backend.delete = mocker.AsyncMock()
        self.mock_backend.exists = mocker.AsyncMock(return_value=False)
        mocker.patch(
            "services.media_service.get_storage_backend",
            return_value=self.mock_backend,
        )
        mocker.patch("services.media_service.SiloService")
        mocker.patch("services.media_service.MediaRepository.delete")
        mocker.patch("services.media_service.MediaRepository.commit")
        mocker.patch("services.media_service.MediaRepository.rollback")

    @pytest.mark.asyncio
    async def test_calls_backend_delete_for_storage_key(self, mocker):
        media = _make_media_orm(mocker, storage_key="repositories/1/7.mp4")
        mocker.patch("services.media_service.MediaRepository.get_by_id", return_value=media)

        result = await MediaService.delete_media(
            media_id=7, app_id=1, repository_id=1, db=mocker.MagicMock()
        )

        assert result is True
        self.mock_backend.delete.assert_any_call("repositories/1/7.mp4")

    @pytest.mark.asyncio
    async def test_also_deletes_audio_key_when_audio_file_exists(self, mocker):
        media = _make_media_orm(mocker, storage_key="repositories/1/7.mp4")
        mocker.patch("services.media_service.MediaRepository.get_by_id", return_value=media)
        self.mock_backend.exists.return_value = True  # audio file exists in storage

        await MediaService.delete_media(
            media_id=7, app_id=1, repository_id=1, db=mocker.MagicMock()
        )

        deleted_keys = [str(c.args[0]) for c in self.mock_backend.delete.call_args_list]
        assert "repositories/1/7.mp4" in deleted_keys
        assert "repositories/1/7_audio.wav" in deleted_keys

    @pytest.mark.asyncio
    async def test_does_not_delete_audio_when_audio_file_missing(self, mocker):
        media = _make_media_orm(mocker, storage_key="repositories/1/7.mp4")
        mocker.patch("services.media_service.MediaRepository.get_by_id", return_value=media)
        self.mock_backend.exists.return_value = False  # no audio file

        await MediaService.delete_media(
            media_id=7, app_id=1, repository_id=1, db=mocker.MagicMock()
        )

        # Only the primary file should have been deleted
        assert self.mock_backend.delete.call_count == 1

    @pytest.mark.asyncio
    async def test_does_not_call_backend_when_storage_key_is_none(self, mocker):
        media = _make_media_orm(mocker, storage_key=None)
        mocker.patch("services.media_service.MediaRepository.get_by_id", return_value=media)

        result = await MediaService.delete_media(
            media_id=7, app_id=1, repository_id=1, db=mocker.MagicMock()
        )

        assert result is True
        self.mock_backend.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_call_backend_when_storage_key_is_empty_string(self, mocker):
        media = _make_media_orm(mocker, storage_key="")
        mocker.patch("services.media_service.MediaRepository.get_by_id", return_value=media)

        result = await MediaService.delete_media(
            media_id=7, app_id=1, repository_id=1, db=mocker.MagicMock()
        )

        assert result is True
        self.mock_backend.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_false_when_media_record_not_found(self, mocker):
        mocker.patch("services.media_service.MediaRepository.get_by_id", return_value=None)

        result = await MediaService.delete_media(
            media_id=99, app_id=1, repository_id=1, db=mocker.MagicMock()
        )

        assert result is False
        self.mock_backend.delete.assert_not_called()
