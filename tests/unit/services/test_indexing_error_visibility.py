"""Indexing failures are stored where users see them (resource, media, service) instead of only logged."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import openai
import pytest
from langchain_core.documents import Document

from models.ai_service import AIService
from models.embedding_service import EmbeddingService
from models.resource import RESOURCE_STATUS_ERROR, RESOURCE_STATUS_INDEXED
from services.silo_service import ResourceIndexingError, ResourceNotIndexableError


def _revoked_key_error():
    request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    return openai.AuthenticationError(
        "Incorrect API key provided: sk-proj-***LRsA", response=httpx.Response(401, request=request), body=None
    )


def _resource():
    embedding = SimpleNamespace(service_id=10, name="text-embedding-3-small", last_error=None)
    silo = SimpleNamespace(silo_id=114, embedding_service=embedding)
    return SimpleNamespace(
        resource_id=54, repository_id=80, uri="cv.pdf", folder_id=None, status=None, error_message=None,
        repository=SimpleNamespace(silo_id=114, silo=silo),
    )


@pytest.fixture
def index_env():
    """Run SiloService.index_resource against an in-memory resource; yield (resource, store, health)."""
    from services import silo_service

    resource = _resource()
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = resource
    store = MagicMock()
    with patch.object(silo_service, "SessionLocal", return_value=session), \
            patch.object(silo_service, "_get_vector_store", return_value=store), \
            patch.object(
                silo_service.SiloService,
                "extract_documents_from_file",
                return_value=[Document(page_content="Resource content", metadata={})],
            ), \
            patch.object(silo_service, "ServiceHealthService") as health:
        yield resource, store, health


class TestResourceIndexingStatus:
    def test_structured_pdf_marker_is_not_indexed(self, index_env):
        from services.silo_service import SiloService

        resource, store, _ = index_env
        document = Document(
            page_content="Structured PDF content",
            metadata={"_aict_structured_pdf_chunk": True},
        )

        with patch.object(SiloService, "extract_documents_from_file", return_value=[document]):
            SiloService.index_resource(resource)

        indexed_docs = store.index_documents.call_args.args[1]
        assert "_aict_structured_pdf_chunk" not in indexed_docs[0].metadata

    def test_success_marks_indexed_and_clears_service_error(self, index_env):
        from services.silo_service import SiloService
        resource, _, health = index_env

        SiloService.index_resource(resource)

        assert resource.status == RESOURCE_STATUS_INDEXED
        assert resource.error_message is None
        health.record_success.assert_called_once_with(EmbeddingService, resource.repository.silo.embedding_service)

    def test_rejected_key_is_stored_on_resource_and_service(self, index_env):
        from services.silo_service import SiloService
        resource, store, health = index_env
        store.index_documents.side_effect = _revoked_key_error()

        with pytest.raises(ResourceIndexingError) as raised:
            SiloService.index_resource(resource)

        assert str(raised.value) == resource.error_message
        assert resource.status == RESOURCE_STATUS_ERROR
        assert "text-embedding-3-small" in resource.error_message
        assert "credentials" in resource.error_message
        assert "LRsA" not in resource.error_message
        model, service, error = health.record_failure.call_args.args
        assert (model, service.service_id) == (EmbeddingService, 10)
        assert error.concerns_service

    def test_no_extracted_text_is_an_error_not_a_silent_skip(self, index_env):
        from services import silo_service
        resource, store, _ = index_env

        with patch.object(silo_service.SiloService, "extract_documents_from_file", return_value=[]), \
                pytest.raises(ResourceNotIndexableError):
            silo_service.SiloService.index_resource(resource)

        store.index_documents.assert_not_called()
        assert resource.status == RESOURCE_STATUS_ERROR
        assert "No text could be extracted" in resource.error_message

    def test_missing_embedding_service_is_an_error(self, index_env):
        from services.silo_service import SiloService
        resource, store, _ = index_env
        resource.repository.silo.embedding_service = None

        with pytest.raises(ResourceNotIndexableError):
            SiloService.index_resource(resource)

        store.index_documents.assert_not_called()
        assert resource.status == RESOURCE_STATUS_ERROR
        assert "no embedding service" in resource.error_message

    def test_failure_before_the_embedding_call_is_stored_without_raw_text(self, index_env):
        from services import silo_service
        resource, _, health = index_env

        with patch.object(silo_service.SiloService, "extract_documents_from_file",
                          side_effect=RuntimeError("cannot open /srv/data/repositories/80/cv.pdf")), \
                pytest.raises(ResourceIndexingError):
            silo_service.SiloService.index_resource(resource)

        assert resource.status == RESOURCE_STATUS_ERROR
        assert resource.error_message.startswith("Indexing failed (RuntimeError)")
        assert "/srv" not in resource.error_message
        health.record_failure.assert_not_called()


class TestUploadReportsIndexingFailures:
    def test_only_failed_resources_are_reported(self):
        from services.resource_service import ResourceService
        ok = SimpleNamespace(resource_id=1, uri="a.pdf", status=RESOURCE_STATUS_INDEXED, error_message=None)
        failed = SimpleNamespace(resource_id=2, uri="b.pdf", status=RESOURCE_STATUS_ERROR, error_message="key rejected")
        legacy = SimpleNamespace(resource_id=3, uri="c.pdf", status=None, error_message=None)

        assert ResourceService.indexing_failures([ok, failed, legacy]) == [
            {"resource_id": 2, "filename": "b.pdf", "error": "key rejected"}
        ]


def _media(tmp_path, embedding_service):
    video = tmp_path / "5.mp4"
    video.write_bytes(b"v")
    silo = SimpleNamespace(
        transcription_service_id=2, video_ai_service_id=None,
        transcription_service=SimpleNamespace(service_id=2, name="whisper", last_error=None), video_ai_service=None,
        embedding_service=embedding_service,
    )
    return SimpleNamespace(
        media_id=5, silo_id=7, repository_id=1, source_type="upload", file_path=str(video),
        forced_language=None, chunk_min_duration=None, chunk_max_duration=None, chunk_overlap=None,
        silo=silo, status="pending", error_message=None,
    )


class TestMediaPipelineErrors:
    def _run(self, media, tmp_path, **patches):
        from tasks import media_tasks
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = media
        transcription = {"language": "es", "duration": 10, "segments": [{"text": "hola"}]}
        with patch.object(media_tasks, "SessionLocal", return_value=db), \
                patch.object(media_tasks, "_has_audio_stream", return_value=True), \
                patch.object(media_tasks, "_extract_audio", return_value=str(tmp_path / "5_audio.wav")), \
                patch.object(media_tasks.TranscriptionService, "transcribe_audio",
                             **patches.get("transcribe", {"return_value": transcription})), \
                patch.object(media_tasks.TranscriptionService, "create_chunks", return_value=[{"text": "hola"}]), \
                patch.object(media_tasks.SiloService, "index_media_chunk") as index, \
                patch.object(media_tasks, "ServiceHealthService") as health:
            media_tasks.process_media_task_sync(5)
        return index, health

    def test_rejected_transcription_key_is_readable_and_flags_the_service(self, tmp_path):
        media = _media(tmp_path, SimpleNamespace(service_id=3, name="emb"))

        _, health = self._run(media, tmp_path, transcribe={"side_effect": _revoked_key_error()})

        assert media.status == "error"
        assert "Transcription service 'whisper'" in media.error_message
        assert "credentials" in media.error_message
        model, service, _ = health.record_failure.call_args.args
        assert (model, service.service_id) == (AIService, 2)

    def test_missing_embedding_service_fails_instead_of_ready_with_nothing_indexed(self, tmp_path):
        media = _media(tmp_path, None)

        index, _ = self._run(media, tmp_path)

        index.assert_not_called()
        assert media.status == "error"
        assert "no embedding service" in media.error_message

    def test_success_clears_service_errors(self, tmp_path):
        embedding = SimpleNamespace(service_id=3, name="emb", last_error=None)
        media = _media(tmp_path, embedding)

        _, health = self._run(media, tmp_path)

        assert media.status == "ready"
        health.record_success.assert_any_call(AIService, media.silo.transcription_service)
        health.record_success.assert_any_call(EmbeddingService, embedding)


class TestServiceWarnings:
    def test_distinct_errors_of_the_silo_services(self):
        from services.silo_service import SiloService
        broken = SimpleNamespace(last_error="key rejected")
        silo = SimpleNamespace(
            embedding_service=broken,
            transcription_service=SimpleNamespace(last_error=None),
            video_ai_service=broken,  # same service twice: reported once
        )
        assert SiloService.service_warnings(silo) == ["key rejected"]

    def test_no_silo_no_warnings(self):
        from services.silo_service import SiloService
        assert SiloService.service_warnings(None) == []


class TestSetIndexStatus:
    def test_storage_failure_does_not_hide_the_indexing_result(self):
        from services.silo_service import SiloService
        session = MagicMock()
        session.commit.side_effect = RuntimeError("db down")

        SiloService._set_index_status(_resource(), session, "boom")  # must not raise

        session.rollback.assert_called_once()


class TestUploadResponse:
    def _upload(self, resources):
        from services import resource_service
        db = MagicMock()
        with patch.object(resource_service.ResourceRepository, "get_repository_by_id", return_value=object()), \
                patch.object(resource_service.ResourceService, "create_multiple_resources",
                             return_value=(resources, [])):
            return resource_service.ResourceService.upload_resources_to_repository(1, 80, ["f"], db)

    def test_indexing_failures_are_reported(self):
        failed = SimpleNamespace(resource_id=2, uri="b.pdf", repository_id=80, create_date=None, type=".pdf",
                                 status=RESOURCE_STATUS_ERROR, error_message="key rejected")

        result = self._upload([failed])

        assert "could not be indexed" in result["message"]
        assert result["indexing_failures"] == [{"resource_id": 2, "filename": "b.pdf", "error": "key rejected"}]
        assert result["created_resources"][0]["status"] == RESOURCE_STATUS_ERROR

    def test_clean_upload_keeps_the_success_message(self):
        ok = SimpleNamespace(resource_id=1, uri="a.pdf", repository_id=80, create_date=None, type=".pdf",
                             status=RESOURCE_STATUS_INDEXED, error_message=None)

        result = self._upload([ok])

        assert result["message"].startswith("Successfully uploaded 1 files")
        assert result["indexing_failures"] == []
