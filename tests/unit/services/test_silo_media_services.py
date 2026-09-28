"""Media (video/audio) indexing driven by the silo's own media services."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

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
        assert (silo.transcription_service_id, silo.video_ai_service_id) == (1, 2)

    def test_system_services_are_allowed(self):
        silo = SimpleNamespace(transcription_service_id=None, video_ai_service_id=None)
        SiloService.apply_media_services(silo, 1, None, 3, _db_with_services(_service(1, app_id=None)))
        assert silo.transcription_service_id == 1

    def test_none_clears(self):
        silo = SimpleNamespace(transcription_service_id=1, video_ai_service_id=2)
        SiloService.apply_media_services(silo, None, None, 3, _db_with_services())
        assert (silo.transcription_service_id, silo.video_ai_service_id) == (None, None)

    def test_rejects_services_of_other_apps(self):
        silo = SimpleNamespace(transcription_service_id=None, video_ai_service_id=None)
        with pytest.raises(ValidationError, match="not found"):
            SiloService.apply_media_services(silo, 1, None, 3, _db_with_services(_service(1, app_id=99)))

    def test_video_service_must_support_video(self):
        silo = SimpleNamespace(transcription_service_id=None, video_ai_service_id=None)
        with pytest.raises(ValidationError, match="does not support video"):
            SiloService.apply_media_services(silo, None, 2, 3, _db_with_services(_service(2)))


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
        assert metadata["silo_id"] == 7 and metadata["repository_id"] is None
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
        assert not video.exists() and not audio.exists()

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
        assert media.status == "error" and media.file_path is None
        assert not video.exists()
        db.delete.assert_not_called()


class TestRemoveSiloMediaFiles:
    def test_removes_only_the_silo_folder(self, tmp_path, monkeypatch):
        monkeypatch.setenv("REPO_BASE_FOLDER", str(tmp_path))
        target, other = tmp_path / "silo_media" / "7", tmp_path / "silo_media" / "8"
        target.mkdir(parents=True)
        other.mkdir(parents=True)
        SiloService.remove_silo_media_files(7)
        assert not target.exists() and other.exists()

    def test_rejects_non_integer_ids(self, tmp_path, monkeypatch):
        monkeypatch.setenv("REPO_BASE_FOLDER", str(tmp_path))
        with pytest.raises(ValueError):
            SiloService.remove_silo_media_files("../../etc")
