"""A retired embedding service blocks embedding computation but never delete/count/cleanup (AD-5, AD-13)."""

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.resource import RESOURCE_STATUS_ERROR
from services import silo_service
from services.silo_service import ResourceIndexingError, SiloService
from utils.error_handlers import handle_database_errors
from utils.service_lifecycle import ServiceRetiredError

PAST = datetime.now(timezone.utc) - timedelta(days=3)


@pytest.fixture
def lifecycle_caplog(caplog):
    from utils import service_lifecycle

    service_lifecycle.logger.addHandler(caplog.handler)
    caplog.set_level(logging.DEBUG)
    yield caplog
    service_lifecycle.logger.removeHandler(caplog.handler)


def _retired_embedding(notice=None):
    return SimpleNamespace(service_id=10, app_id=3, name="emb-old", end_of_service_at=PAST,
                           deprecation_notice=notice, last_error=None)


def _silo(embedding=None):
    embedding = embedding or _retired_embedding()
    return SimpleNamespace(silo_id=7, app_id=3, embedding_service_id=10, embedding_service=embedding,
                           vector_db_type="PGVECTOR")


@pytest.fixture
def store():
    s = MagicMock()
    with patch.object(silo_service, "_get_vector_store", return_value=s):
        yield s


def _assert_embedding_message(exc: ServiceRetiredError):
    assert "emb-old" in exc.message
    assert "re-indexed" in exc.message


class TestGuardedEntryPoints:
    def test_get_silo_retriever(self, store):
        session = MagicMock()
        with patch.object(silo_service, "SessionLocal", return_value=session), \
                patch.object(SiloService, "get_silo", return_value=_silo()):
            with pytest.raises(ServiceRetiredError) as raised:
                SiloService.get_silo_retriever(7)
        _assert_embedding_message(raised.value)
        store.get_retriever.assert_not_called()
        session.close.assert_called_once()

    def test_index_multiple_content(self, store):
        silo = _silo()
        with patch.object(silo_service.SiloRepository, "get_by_id", return_value=silo), \
                patch.object(silo_service.SiloRepository, "get_embedding_service_by_id",
                             return_value=silo.embedding_service):
            with pytest.raises(ServiceRetiredError) as raised:
                SiloService.index_multiple_content(7, [{"content": "x"}], MagicMock())
        _assert_embedding_message(raised.value)
        store.index_documents.assert_not_called()

    def test_index_single_content_is_covered(self, store):
        silo = _silo()
        with patch.object(silo_service.SiloRepository, "get_by_id", return_value=silo), \
                patch.object(silo_service.SiloRepository, "get_embedding_service_by_id",
                             return_value=silo.embedding_service):
            with pytest.raises(ServiceRetiredError):
                SiloService.index_single_content(7, "x", {}, MagicMock())
        store.index_documents.assert_not_called()

    def test_index_media_chunk(self, store):
        media = SimpleNamespace(media_id=5, silo_id=7, silo=_silo(), folder_id=None, file_path="/x/5.mp4",
                                custom_metadata=None, repository_id=None, name="n", source_type="upload",
                                source_url=None, language="es", processing_mode=None, duration=1)
        with pytest.raises(ServiceRetiredError) as raised:
            SiloService.index_media_chunk({"text": "hola"}, media, db=MagicMock())
        _assert_embedding_message(raised.value)
        store.index_documents.assert_not_called()

    def test_find_docs_in_collection(self, store):
        silo = _silo()
        with patch.object(silo_service.SiloRepository, "get_by_id", return_value=silo), \
                patch.object(SiloService, "check_silo_collection_exists", return_value=True), \
                patch.object(silo_service.SiloRepository, "get_embedding_service_by_id",
                             return_value=silo.embedding_service):
            with pytest.raises(ServiceRetiredError) as raised:
                SiloService.find_docs_in_collection(7, "q", db=MagicMock())
            with pytest.raises(ServiceRetiredError):
                SiloService.search_in_silo(7, "q", db=MagicMock())
            with pytest.raises(ServiceRetiredError):
                SiloService.get_neighboring_chunks(7, "media", "5", db=MagicMock())
        _assert_embedding_message(raised.value)
        store.search_similar_documents.assert_not_called()

    def test_active_service_is_not_blocked(self, store):
        active = SimpleNamespace(service_id=10, app_id=3, name="emb", end_of_service_at=None)
        silo = _silo(active)
        store.search_similar_documents.return_value = []
        with patch.object(silo_service.SiloRepository, "get_by_id", return_value=silo), \
                patch.object(SiloService, "check_silo_collection_exists", return_value=True), \
                patch.object(silo_service.SiloRepository, "get_embedding_service_by_id", return_value=active):
            assert SiloService.find_docs_in_collection(7, "q", db=MagicMock()) == []
        store.search_similar_documents.assert_called_once()

    def test_blocked_call_logs_exactly_one_warning(self, store, lifecycle_caplog):
        session = MagicMock()
        with patch.object(silo_service, "SessionLocal", return_value=session), \
                patch.object(SiloService, "get_silo", return_value=_silo(_retired_embedding("Switch to X."))):
            with pytest.raises(ServiceRetiredError):
                SiloService.get_silo_retriever(7)
        records = [r for r in lifecycle_caplog.records if r.levelno >= logging.WARNING]
        assert len(records) == 1 and records[0].levelno == logging.WARNING


class TestCleanupStillWorks:
    def test_delete_collection_and_docs_and_count_reach_the_store(self, store):
        silo = _silo()
        db = MagicMock()
        store.collection_exists.return_value = True
        store.count_documents.return_value = 4
        with patch.object(silo_service.SiloRepository, "get_by_id", return_value=silo), \
                patch.object(SiloService, "get_silo", return_value=silo):
            SiloService.delete_collection(7, db)
            SiloService.delete_docs_in_collection(7, ["a"], db)
            SiloService.delete_all_docs_in_collection(7, db)
            SiloService.count_docs_in_silo(7, db)
        assert store.method_calls, "the vector store must still be used for cleanup"
        names = {c[0] for c in store.method_calls}
        assert {"delete_collection", "delete_documents", "count_documents"} <= names


class TestIndexResourceRetired:
    def test_stores_error_and_skips_health_record(self, lifecycle_caplog):
        embedding = _retired_embedding()
        silo = _silo(embedding)
        resource = SimpleNamespace(
            resource_id=54, repository_id=80, uri="cv.pdf", folder_id=None, status=None, error_message=None,
            repository=SimpleNamespace(silo_id=7, silo=silo),
        )
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = resource
        store = MagicMock()
        with patch.object(silo_service, "SessionLocal", return_value=session), \
                patch.object(silo_service, "_get_vector_store", return_value=store), \
                patch.object(SiloService, "extract_documents_from_file", return_value=["doc"]), \
                patch.object(silo_service, "ServiceHealthService") as health:
            with pytest.raises(ResourceIndexingError) as raised:
                SiloService.index_resource(resource)

        assert resource.status == RESOURCE_STATUS_ERROR
        assert embedding.last_error is None
        assert resource.error_message == str(raised.value)
        assert "re-indexed" in resource.error_message
        store.index_documents.assert_not_called()
        health.record_failure.assert_not_called()
        warnings = [r for r in lifecycle_caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1
        assert "channel=repository_indexing" in warnings[0].getMessage()


class TestDecoratorDoesNotRelog:
    def test_service_retired_passes_through_silently(self, lifecycle_caplog):
        from utils import error_handlers

        error_handlers.logger.addHandler(lifecycle_caplog.handler)
        try:
            @handle_database_errors("op")
            def blocked():
                raise ServiceRetiredError(_retired_embedding("secret notice"), "embedding")

            with pytest.raises(ServiceRetiredError):
                blocked()
        finally:
            error_handlers.logger.removeHandler(lifecycle_caplog.handler)
        assert not [r for r in lifecycle_caplog.records if r.levelno >= logging.WARNING]


class TestSharePointStoresRetirementMessage:
    def test_per_file_error_text_equals_message(self):
        exc = ServiceRetiredError(_retired_embedding(), "embedding")
        assert str(exc) == exc.message


# ---------------------------------------------------------------------------
# Media task
# ---------------------------------------------------------------------------

def _media_env(tmp_path, *, retired="embedding", video=False):
    from tasks import media_tasks  # noqa: F401

    emb = _retired_embedding() if retired == "embedding" else SimpleNamespace(service_id=3, name="emb")
    silo = SimpleNamespace(
        transcription_service_id=2, video_ai_service_id=4 if video else None,
        transcription_service=None, video_ai_service=None, embedding_service=emb,
    )
    video_file = tmp_path / "5.mp4"
    video_file.write_bytes(b"v")
    media = SimpleNamespace(media_id=5, silo_id=7, repository_id=None, source_type="upload",
                            file_path=str(video_file), forced_language=None, chunk_min_duration=None,
                            chunk_max_duration=None, chunk_overlap=None, status=None, error_message=None,
                            silo=silo)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = media
    return media, db


def _run_media(media, db, tmp_path, *, transcribe=None, analyze=None, index=None):
    from tasks import media_tasks

    transcription = {"language": "es", "duration": 10, "segments": [{"text": "hola"}]}
    with patch.object(media_tasks, "SessionLocal", return_value=db), \
            patch.object(media_tasks, "ServiceHealthService") as health, \
            patch.object(media_tasks, "_has_audio_stream", return_value=True), \
            patch.object(media_tasks, "_has_video_stream", return_value=True), \
            patch.object(media_tasks, "_extract_audio", return_value=str(tmp_path / "5_audio.wav")), \
            patch.object(media_tasks.TranscriptionService, "transcribe_audio",
                         side_effect=transcribe, return_value=transcription), \
            patch.object(media_tasks.TranscriptionService, "create_chunks", return_value=[{"text": "hola"}]), \
            patch.object(media_tasks.VideoAnalysisService, "analyze_video", side_effect=analyze), \
            patch.object(media_tasks.SiloService, "index_media_chunk", side_effect=index):
        media_tasks.process_media_task_sync(5)
    return health


class TestMediaTaskRetired:
    def test_retired_embedding_fails_before_transcription(self, tmp_path, lifecycle_caplog):
        media, db = _media_env(tmp_path)
        err = ServiceRetiredError(media.silo.embedding_service, "embedding")
        from tasks import media_tasks

        with patch.object(media_tasks.TranscriptionService, "transcribe_audio") as transcribe:
            health = _run_media(media, db, tmp_path)
        assert media.status == "error"
        assert media.error_message == err.message[:500]
        transcribe.assert_not_called()
        health.record_failure.assert_not_called()
        warnings = [r for r in lifecycle_caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1
        assert "channel=media_task" in warnings[0].getMessage()

    def test_retired_embedding_mid_pipeline_is_the_backstop(self, tmp_path):
        media, db = _media_env(tmp_path, retired=None)
        err = ServiceRetiredError(_retired_embedding(), "embedding")
        health = _run_media(media, db, tmp_path, index=err)
        assert media.status == "error"
        assert media.error_message == err.message[:500]
        assert not health.record_failure.call_args.args[2].concerns_service

    def test_retired_transcription_ends_in_error_with_message(self, tmp_path):
        media, db = _media_env(tmp_path, retired=None)
        err = ServiceRetiredError(SimpleNamespace(service_id=2, name="whisper-old", end_of_service_at=PAST), "ai")
        _run_media(media, db, tmp_path, transcribe=err)
        assert media.status == "error"
        assert media.error_message == err.message

    def test_retired_video_fails_media_instead_of_audio_only(self, tmp_path):
        media, db = _media_env(tmp_path, retired=None, video=True)
        err = ServiceRetiredError(SimpleNamespace(service_id=4, name="vision-old", end_of_service_at=PAST), "ai")
        index = MagicMock()
        _run_media(media, db, tmp_path, analyze=err, index=index.side_effect)
        assert media.status == "error"
        assert media.error_message == err.message
        assert "vision-old" in media.error_message

    def test_other_video_failure_still_falls_back_to_audio_only(self, tmp_path):
        media, db = _media_env(tmp_path, retired=None, video=True)
        _run_media(media, db, tmp_path, analyze=RuntimeError("boom"))
        assert media.status == "ready"


# ---------------------------------------------------------------------------
# Crawl
# ---------------------------------------------------------------------------

def _crawl_env(embedding):
    from models.enums.crawl_job_status import CrawlJobStatus

    job = MagicMock(domain_id=42, status=CrawlJobStatus.QUEUED, indexed_count=0, skipped_count=0,
                    removed_count=0, failed_count=0, discovered_count=0)
    domain = MagicMock(domain_id=42, silo_id=7, content_tag="body", content_id=None, content_class=None, app_id=3)
    domain.silo.embedding_service = embedding
    policy = MagicMock(domain_id=42, seed_url=None, sitemap_url=None, respect_robots_txt=False,
                       rate_limit_rps=10.0, refresh_interval_hours=168)
    url = MagicMock(url="http://e.test/a", normalized_url="http://e.test/a", sitemap_lastmod=None,
                    last_indexed_at=None, content_hash="old", http_etag=None, http_last_modified=None)
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [url]
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session_cm)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    return job, domain, policy, url, db, session_cm


async def _run_crawl(job, domain, policy, db, session_cm, ensure=None):
    from services import crawl_executor_service as ces

    async def no_candidates(*a, **k):
        return
        yield

    fetched = SimpleNamespace(status_code=200, content="<body>new</body>", error=None, etag=None,
                              last_modified=None)
    fetch = AsyncMock(return_value=fetched)
    sleep = AsyncMock()
    ctx = [
        patch.object(ces, "SessionLocal", return_value=db),
        patch.object(ces.CrawlJobRepository, "get_by_id", return_value=job),
        patch.object(ces.CrawlJobRepository, "update"),
        patch.object(ces.DomainRepository, "get_by_id", return_value=domain),
        patch.object(ces.CrawlPolicyRepository, "get_by_domain", return_value=policy),
        patch.object(ces, "discover_urls", side_effect=no_candidates),
        patch.object(ces.aiohttp, "ClientSession", return_value=session_cm),
        patch.object(ces, "fetch", new=fetch),
        patch.object(ces, "extract_text_from_html", return_value="new text"),
        patch.object(ces.asyncio, "sleep", new=sleep),
        patch("services.silo_service.SiloService.delete_url"),
        patch("services.silo_service.SiloService.index_single_content"),
    ]
    if ensure is not None:
        ctx.append(patch.object(ces, "ensure_service_active", side_effect=ensure))
    from contextlib import ExitStack as _ES

    with _ES() as stack:
        mocks = [stack.enter_context(c) for c in ctx]
        await ces.CrawlExecutorService.run_job(1)
    return fetch, sleep, mocks[10], mocks[11]


class TestCrawlRetired:
    @pytest.mark.asyncio
    async def test_retired_at_start_fails_job_once_without_fetching(self, lifecycle_caplog):
        from models.enums.crawl_job_status import CrawlJobStatus

        job, domain, policy, url, db, cm = _crawl_env(_retired_embedding())
        fetch, sleep, delete_url, index = await _run_crawl(job, domain, policy, db, cm)

        assert job.status == CrawlJobStatus.FAILED
        assert "re-indexed" in job.error_log
        fetch.assert_not_called()
        delete_url.assert_not_called()
        warnings = [r for r in lifecycle_caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1
        assert "channel=domain_crawl" in warnings[0].getMessage()

    @pytest.mark.asyncio
    async def test_retired_mid_job_fails_url_and_keeps_the_loop_tail(self):
        from models.enums.domain_url_status import DomainUrlStatus

        embedding = _retired_embedding()
        err = ServiceRetiredError(embedding, "embedding")
        calls = {"n": 0}

        def ensure(service, kind):
            calls["n"] += 1
            if calls["n"] > 1:
                raise err

        job, domain, policy, url, db, cm = _crawl_env(embedding)
        fetch, sleep, delete_url, index = await _run_crawl(job, domain, policy, db, cm, ensure=ensure)

        delete_url.assert_not_called()
        index.assert_not_called()
        assert url.status == DomainUrlStatus.FAILED
        assert url.last_error == err.message
        assert url.content_hash == "old"
        assert job.failed_count == 1
        assert job.indexed_count == 0
        sleep.assert_awaited_once()  # rate limit still applied


class TestQdrantDeleteDoesNotEmbed:
    def test_delete_by_ids_uses_raw_client(self):
        from tools.vector_stores.qdrant_store import QdrantStore

        store = QdrantStore.__new__(QdrantStore)
        store.client = MagicMock()
        store._get_vector_store = MagicMock(side_effect=AssertionError("must not build the embedding store"))
        store.delete_documents("silo_7", ["a", "b"], embedding_service=_retired_embedding())
        kwargs = store.client.delete.call_args.kwargs
        assert kwargs["collection_name"] == "silo_7"
        assert list(kwargs["points_selector"].points) == ["a", "b"]


class TestSharePointRetired:
    @pytest.mark.asyncio
    async def test_retired_exits_before_download_and_keeps_delta_token(self, lifecycle_caplog):
        from models.enums.sharepoint_sync_status import SharePointSyncStatus
        from services.sharepoint import service as sp

        source = SimpleNamespace(
            app_id=3, silo_id=7, silo=_silo(), last_delta_token="tok", last_sync_status=None,
            last_sync_error=None,
        )
        with patch("db.database.SessionLocal", return_value=MagicMock()), \
                patch.object(sp.SharePointSourceRepository, "get_by_id", return_value=source), \
                patch.object(sp.SharePointSourceRepository, "update") as update, \
                patch.object(sp.GraphClient, "get_token", new=AsyncMock()) as token:
            await sp.SharePointSyncService.run_sync(1)

        token.assert_not_awaited()
        update.assert_called_once()
        assert source.last_sync_status == SharePointSyncStatus.ERROR
        assert "re-indexed" in source.last_sync_error
        assert source.last_delta_token == "tok"
        warnings = [r for r in lifecycle_caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1
        assert "channel=sharepoint_sync" in warnings[0].getMessage()
