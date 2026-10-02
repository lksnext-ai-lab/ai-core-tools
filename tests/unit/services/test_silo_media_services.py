"""Media (video/audio) indexing driven by the silo's own media services."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.media_service import MediaService
from services.silo_service import SiloService
from utils.error_handlers import ValidationError


def _db_with_services(*services):
    by_id = {s.service_id: s for s in services}
    db = MagicMock()
    query = MagicMock()
    db.query.return_value = query

    def _filter(criterion):
        found = MagicMock()
        found.first.return_value = by_id.get(criterion.right.value)
        return found

    query.filter.side_effect = _filter
    return db


def _service(service_id, app_id=3, supports_video=False):
    return SimpleNamespace(service_id=service_id, app_id=app_id, supports_video=supports_video)


class TestApplyMediaServices:
    def test_sets_both_services(self):
        silo = SimpleNamespace(transcription_service_id=None, video_ai_service_id=None)
        db = _db_with_services(_service(1), _service(2, supports_video=True))
        SiloService.apply_media_services(silo, 1, 2, 3, db)
        assert silo.transcription_service_id == 1
        assert silo.video_ai_service_id == 2

    def test_system_services_are_allowed(self):
        silo = SimpleNamespace(transcription_service_id=None, video_ai_service_id=None)
        SiloService.apply_media_services(silo, 1, None, 3, _db_with_services(_service(1, app_id=None)))
        assert silo.transcription_service_id == 1

    def test_none_clears(self):
        silo = SimpleNamespace(transcription_service_id=1, video_ai_service_id=2)
        SiloService.apply_media_services(silo, None, None, 3, _db_with_services())
        assert silo.transcription_service_id is None
        assert silo.video_ai_service_id is None

    def test_rejects_services_of_other_apps(self):
        silo = SimpleNamespace(transcription_service_id=None, video_ai_service_id=None)
        db = _db_with_services(_service(1, app_id=99))
        with pytest.raises(ValidationError, match="not found"):
            SiloService.apply_media_services(silo, 1, None, 3, db)

    def test_video_service_must_support_video(self):
        silo = SimpleNamespace(transcription_service_id=None, video_ai_service_id=None)
        db = _db_with_services(_service(2))
        with pytest.raises(ValidationError, match="does not support video"):
            SiloService.apply_media_services(silo, None, 2, 3, db)


class TestIndexMediaChunk:
    def _media(self, **overrides):
        silo = SimpleNamespace(silo_id=7, embedding_service=object())
        values = dict(media_id=5, silo_id=7, silo=silo, repository_id=None, folder_id=None, name="demo",
                      source_type="upload", source_url=None, language="es", file_path="/data/silo_media/7/5.mp4",
                      processing_mode="basic", duration=60.0,
                      custom_metadata={"doc_id": "42", "media_id": "spoofed"})
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_silo_media_carries_caller_metadata_without_overriding_system_keys(self):
        store = MagicMock()
        with patch("services.silo_service._get_vector_store", return_value=store):
            SiloService.index_media_chunk({"text": "hola", "start_time": 0, "end_time": 30, "chunk_index": 0},
                                          self._media(), db=MagicMock())

        collection, docs, _ = store.index_documents.call_args.args
        metadata = docs[0].metadata
        assert collection.endswith("7")
        assert metadata["doc_id"] == "42"
        assert metadata["media_id"] == 5  # system key wins over caller metadata
        assert metadata["silo_id"] == 7
        assert metadata["repository_id"] is None
        assert metadata["ref"] == "silo_media/7/5.mp4"

    def test_skips_silo_without_embedding_service(self):
        media = self._media(silo=SimpleNamespace(silo_id=7, embedding_service=None))
        with patch("services.silo_service._get_vector_store") as store:
            SiloService.index_media_chunk({"text": "x"}, media, db=MagicMock())
        store.assert_not_called()


class TestMediaTaskUsesSiloServices:
    def test_missing_transcription_service_on_silo_marks_error(self):
        from tasks import media_tasks

        media = SimpleNamespace(media_id=5, silo_id=7, repository_id=None, source_type="upload",
                                file_path="/x/5.mp4", silo=SimpleNamespace(transcription_service_id=None,
                                                                           video_ai_service_id=None))
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = media
        with patch.object(media_tasks, "SessionLocal", return_value=db):
            media_tasks.process_media_task_sync(5)
        assert media.status == "error"
        assert "No transcription service configured on silo 7" in media.error_message

    def test_storage_folder(self, monkeypatch):
        from tasks import media_tasks

        monkeypatch.setattr(media_tasks, "REPO_BASE_FOLDER", "/base")
        assert media_tasks.media_storage_folder(SimpleNamespace(repository_id=3, silo_id=7)) == "/base/3"
        assert media_tasks.media_storage_folder(SimpleNamespace(repository_id=None, silo_id=7)) == "/base/silo_media/7"


class TestSiloMediaLeavesNothingBehind:
    def test_discard_removes_file_and_extracted_audio(self, tmp_path):
        from tasks import media_tasks

        video, audio = tmp_path / "5.mp4", tmp_path / "5_audio.wav"
        video.write_bytes(b"v")
        audio.write_bytes(b"a")
        media_tasks._discard_silo_media_files(SimpleNamespace(file_path=str(video)))
        assert not video.exists()
        assert not audio.exists()

    def test_indexed_chunk_source_is_the_original_name(self):
        store = MagicMock()
        media = TestIndexMediaChunk()._media()
        with patch("services.silo_service._get_vector_store", return_value=store):
            SiloService.index_media_chunk({"text": "x"}, media, db=MagicMock())
        assert store.index_documents.call_args.args[1][0].metadata["source"] == "demo.mp4"

    def test_failed_silo_media_keeps_the_error_but_not_the_file(self, tmp_path):
        from tasks import media_tasks

        video = tmp_path / "5.mp4"
        video.write_bytes(b"v")
        media = SimpleNamespace(media_id=5, silo_id=7, repository_id=None, source_type="upload",
                                file_path=str(video), silo=SimpleNamespace(transcription_service_id=None,
                                                                           video_ai_service_id=None))
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = media
        with patch.object(media_tasks, "SessionLocal", return_value=db):
            media_tasks.process_media_task_sync(5)
        assert media.status == "error"
        assert media.file_path is None
        assert not video.exists()
        db.delete.assert_not_called()


class TestRemoveSiloMediaFiles:
    def test_removes_only_the_silo_folder(self, tmp_path, monkeypatch):
        monkeypatch.setenv("REPO_BASE_FOLDER", str(tmp_path))
        target, other = tmp_path / "silo_media" / "7", tmp_path / "silo_media" / "8"
        target.mkdir(parents=True)
        other.mkdir(parents=True)
        SiloService.remove_silo_media_files(7)
        assert not target.exists()
        assert other.exists()

    def test_rejects_non_integer_ids(self, tmp_path, monkeypatch):
        monkeypatch.setenv("REPO_BASE_FOLDER", str(tmp_path))
        with pytest.raises(ValueError):
            SiloService.remove_silo_media_files("../../etc")


def _media_silo(**overrides):
    values = dict(silo_id=7, embedding_service_id=1, transcription_service_id=2)
    values.update(overrides)
    return SimpleNamespace(**values)


def _upload(filename, content=b"v"):
    file = MagicMock()
    file.filename = filename
    file.read = AsyncMock(return_value=content)
    return file


class TestSiloAcceptsMedia:
    def test_requires_embedding_service(self):
        with pytest.raises(ValueError, match="no embedding service"):
            MediaService.check_silo_accepts_media(_media_silo(embedding_service_id=None))

    def test_requires_transcription_service(self):
        with pytest.raises(ValueError, match="no transcription service"):
            MediaService.check_silo_accepts_media(_media_silo(transcription_service_id=None))

    @pytest.mark.parametrize("filename, expected", [("a.MP4", True), ("a.mp3", True), ("a.pdf", False), (None, False)])
    def test_is_media_filename(self, filename, expected):
        assert MediaService.is_media_filename(filename) is expected


class TestCreateSiloMedia:
    @pytest.mark.asyncio
    async def test_upload_is_stored_in_the_silo_media_folder(self, tmp_path, monkeypatch):
        from tasks import media_tasks

        monkeypatch.setattr(media_tasks, "REPO_BASE_FOLDER", str(tmp_path))
        db = MagicMock()
        db.flush.side_effect = lambda: setattr(db.add.call_args.args[0], "media_id", 5)
        background = MagicMock()

        media = await MediaService.create_silo_media_from_file(
            _upload("clip.mp4"), _media_silo(), db, background, metadata={"doc_id": "42"},
        )

        assert media.repository_id is None
        assert media.custom_metadata == {"doc_id": "42"}
        assert media.file_path == str(tmp_path / "silo_media" / "7" / "5.mp4")
        assert (tmp_path / "silo_media" / "7" / "5.mp4").read_bytes() == b"v"
        background.add_task.assert_called_once_with(media_tasks.process_media_task_sync, 5)

    @pytest.mark.asyncio
    async def test_upload_rejects_non_media(self):
        with pytest.raises(ValueError, match="Unsupported file type"):
            await MediaService.create_silo_media_from_file(_upload("doc.pdf"), _media_silo(), MagicMock(), MagicMock())

    @pytest.mark.asyncio
    async def test_youtube_is_scoped_to_the_silo(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        background = MagicMock()

        media = await MediaService.create_silo_media_from_youtube(
            "https://youtu.be/abc", _media_silo(), db, background, metadata={"topic": "demo"},
        )

        assert media.silo_id == 7
        assert media.repository_id is None
        assert media.custom_metadata == {"topic": "demo"}
        background.add_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_youtube_in_the_silo_is_rejected(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(media_id=9)
        silo = _media_silo()

        with pytest.raises(ValueError, match="already exists in this silo"):
            await MediaService.create_silo_media_from_youtube("https://youtu.be/abc", silo, db, MagicMock())

    @pytest.mark.asyncio
    async def test_invalid_youtube_url(self):
        with pytest.raises(ValueError, match="Invalid YouTube URL"):
            await MediaService.create_silo_media_from_youtube("https://example.com", _media_silo(), MagicMock(), MagicMock())

    def test_repository_silo_id(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.scalar.return_value = 7
        assert MediaService._repository_silo_id(3, db) == 7

    def test_unknown_repository(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.scalar.return_value = None
        with pytest.raises(ValueError, match="Repository 3 not found"):
            MediaService._repository_silo_id(3, db)


class TestDeleteMediaItem:
    def test_removes_vectors_files_and_row(self, tmp_path):
        video, audio = tmp_path / "5.mp4", tmp_path / "5_audio.wav"
        video.write_bytes(b"v")
        audio.write_bytes(b"a")
        media = SimpleNamespace(media_id=5, file_path=str(video))
        with patch("services.media_service.SiloService.delete_media") as delete_vectors, \
                patch("services.media_service.MediaRepository") as repo:
            assert MediaService.delete_media_item(media, MagicMock()) is True
        delete_vectors.assert_called_once_with(media)
        repo.delete.assert_called_once()
        assert not video.exists()
        assert not audio.exists()

    def test_failure_rolls_back(self):
        media = SimpleNamespace(media_id=5, file_path=None)
        with patch("services.media_service.SiloService.delete_media", side_effect=RuntimeError("boom")), \
                patch("services.media_service.MediaRepository") as repo:
            assert MediaService.delete_media_item(media, MagicMock()) is False
        repo.rollback.assert_called_once()

    def test_delete_media_by_id_not_found(self):
        with patch("services.media_service.MediaRepository.get_by_id", return_value=None):
            assert MediaService.delete_media(5, 1, 3, MagicMock()) is False


class TestSiloServiceMediaWiring:
    def test_router_forwards_media_services_only_when_sent(self):
        from schemas.silo_schemas import UpdateSiloSchema

        data = UpdateSiloSchema(name="s", transcription_service_id=2)
        with patch.object(SiloService, "create_or_update_silo") as save:
            SiloService.create_or_update_silo_router(3, 7, data, MagicMock())
        form = save.call_args.args[0]
        assert form["transcription_service_id"] == 2
        assert "video_ai_service_id" not in form

    def test_delete_silo_router_removes_media_files(self):
        with patch("services.silo_service.SiloRepository.delete", return_value=True), \
                patch.object(SiloService, "remove_silo_media_files") as remove:
            assert SiloService.delete_silo_router(7, MagicMock()) is True
        remove.assert_called_once_with(7)

    def test_delete_silo_router_keeps_files_when_nothing_deleted(self):
        with patch("services.silo_service.SiloRepository.delete", return_value=False), \
                patch.object(SiloService, "remove_silo_media_files") as remove:
            assert SiloService.delete_silo_router(7, MagicMock()) is False
        remove.assert_not_called()

    def test_remove_files_without_base_folder_is_noop(self, monkeypatch):
        monkeypatch.delenv("REPO_BASE_FOLDER", raising=False)
        assert SiloService.remove_silo_media_files(7) is None

    def test_media_ai_service_options(self):
        app_service = SimpleNamespace(service_id=1, name="whisper", supports_video=None)
        system_service = SimpleNamespace(service_id=2, name="gemini", supports_video=True)
        with patch("repositories.ai_service_repository.AIServiceRepository.get_by_app_id", return_value=[app_service]), \
                patch("repositories.ai_service_repository.AIServiceRepository.get_system_services",
                      return_value=[system_service]):
            options = SiloService.media_ai_service_options(3, MagicMock())
        assert options == [
            {"service_id": 1, "name": "whisper", "supports_video": False},
            {"service_id": 2, "name": "gemini", "supports_video": True},
        ]


class TestRepositoryMediaServicesReadThrough:
    def test_values_come_from_the_silo(self):
        from models.repository import Repository

        repo = Repository()
        repo.silo = SimpleNamespace(transcription_service_id=2, video_ai_service_id=4)
        assert repo.transcription_service_id == 2
        assert repo.video_ai_service_id == 4


class TestSiloMediaTaskSuccess:
    def test_indexed_silo_media_leaves_nothing_behind(self, tmp_path):
        from tasks import media_tasks

        video = tmp_path / "5.mp4"
        video.write_bytes(b"v")
        media = SimpleNamespace(media_id=5, silo_id=7, repository_id=None, source_type="upload",
                                file_path=str(video), forced_language=None, chunk_min_duration=None,
                                chunk_max_duration=None, chunk_overlap=None,
                                silo=SimpleNamespace(transcription_service_id=2, video_ai_service_id=None))
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = media
        transcription = {"language": "es", "duration": 10, "segments": [{"text": "hola"}]}
        with patch.object(media_tasks, "SessionLocal", return_value=db), \
                patch.object(media_tasks, "_has_audio_stream", return_value=True), \
                patch.object(media_tasks, "_extract_audio", return_value=str(tmp_path / "5_audio.wav")), \
                patch.object(media_tasks.TranscriptionService, "transcribe_audio", return_value=transcription), \
                patch.object(media_tasks.TranscriptionService, "create_chunks", return_value=[{"text": "hola"}]), \
                patch.object(media_tasks.SiloService, "index_media_chunk") as index:
            media_tasks.process_media_task_sync(5)

        index.assert_called_once()
        assert media.status == "ready"
        assert not video.exists()
        db.delete.assert_called_once_with(media)
