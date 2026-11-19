"""Chat upload: the embedding work runs in a worker thread with its own DB session and a timeout (never on the loop)."""
import asyncio
import contextlib
import io
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import UploadFile

from services import chat_attachment_service as module
from services.chat_attachment_service import ChatAttachmentService
from utils.service_lifecycle import ServiceRetiredError

FILE_REF = SimpleNamespace(
    file_id="f1", filename="a.txt", file_type="text", content="hello", file_path="p/a.txt", file_size_bytes=5,
    processing_status="ok", content_preview="hello", has_extractable_content=True, mime_type="text/plain",
)


class _Files:
    discarded = False

    async def upload_file(self, **kwargs):
        return FILE_REF

    async def discard_uploaded_file(self, *args):
        _Files.discarded = True


def _session_factory(sessions):
    @contextlib.contextmanager
    def opener():
        session = MagicMock(name="worker-session")
        session.thread = threading.get_ident()
        sessions.append(session)
        yield session

    return opener


async def _upload(request_db, timeout=0.3, degrade=True):
    return await ChatAttachmentService.upload(
        request_db, UploadFile(filename="a.txt", file=io.BytesIO(b"hello")), agent_id=1, app_id=2, user_context={},
        conversation_id=3, has_memory=True, resolve_session_id=lambda: "conv_1_x", embedding_service_id=9,
        degrade_when_retired=degrade, index_timeout_seconds=timeout,
    )


@pytest.fixture(autouse=True)
def _fake_files():
    with patch.object(module, "FileManagementService", _Files):
        yield


async def test_indexing_runs_in_a_worker_thread_with_a_fresh_session_not_the_request_one():
    seen, sessions = {}, []

    def fake_vectorize(**kwargs):
        seen.update(kwargs, thread=threading.get_ident())
        return True

    request_db = MagicMock(name="request-session")
    with patch.object(module, "open_indexing_session", _session_factory(sessions)), \
            patch.object(module.PlaygroundMediaService, "vectorize_uploaded_file", fake_vectorize):
        result = await _upload(request_db)
    assert result["vectorized"] is True
    assert seen["thread"] != threading.get_ident()
    assert seen["db"] is sessions[0] and seen["db"] is not request_db
    assert seen["embedding_service_id"] == 9 and seen["session_id"] == "conv_1_x"
    request_db.rollback.assert_not_called()  # nothing of the request session is touched by the indexing


async def test_a_slow_embedding_does_not_block_the_loop_and_times_out_to_not_vectorized():
    """No wall-clock assertions: the worker is held on an Event, the outcome is read while it is still held."""
    ticks = 0
    started, release, finished = threading.Event(), threading.Event(), threading.Event()

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0)
            ticks += 1

    def slow(**kwargs):
        started.set()
        release.wait(5)
        finished.set()
        return True

    task = asyncio.create_task(ticker())
    with patch.object(module, "open_indexing_session", _session_factory([])), \
            patch.object(module.PlaygroundMediaService, "vectorize_uploaded_file", slow):
        result = await _upload(MagicMock(), timeout=0.3)
        # the outcome is known while the provider call is STILL running (release is unset)
        assert await asyncio.to_thread(started.wait, 2) and not release.is_set() and not finished.is_set()
        task.cancel()
        assert result["vectorized"] is False and result["success"] is True and result["file_id"] == "f1"
        assert ticks >= 3  # the event loop kept running while the worker was held
        release.set()
        assert await asyncio.to_thread(finished.wait, 5)  # let the abandoned worker end before the patches go away


async def test_a_provider_error_degrades_and_logs_only_the_class():
    def broken(**kwargs):
        raise RuntimeError("secret provider message with the file text hello")

    with patch.object(module, "open_indexing_session", _session_factory([])), \
            patch.object(module.PlaygroundMediaService, "vectorize_uploaded_file", broken), \
            patch.object(module, "logger") as log:
        result = await _upload(MagicMock())
    assert result["vectorized"] is False
    logged = " ".join(str(a) for call in log.warning.call_args_list for a in call.args)
    assert "RuntimeError" in logged and "secret provider message" not in logged


async def test_a_retired_service_degrades_for_the_chat_and_keeps_the_file():
    _Files.discarded = False

    def retired(**kwargs):
        raise ServiceRetiredError(SimpleNamespace(service_id=9, name="e"), "embedding")

    request_db = MagicMock()
    with patch.object(module, "open_indexing_session", _session_factory([])), \
            patch.object(module.PlaygroundMediaService, "vectorize_uploaded_file", retired):
        result = await _upload(request_db)
    assert result["vectorized"] is False and not _Files.discarded
    request_db.rollback.assert_not_called()  # the failed transaction was the worker session's, not the request's


async def test_the_session_is_closed_and_rolled_back_by_the_opener_on_error():
    opened = []
    real = module.open_indexing_session

    class Boom(Exception):
        pass

    def broken(**kwargs):
        raise Boom()

    with patch.object(module, "SessionLocal") as factory, \
            patch.object(module.PlaygroundMediaService, "vectorize_uploaded_file", broken):
        session = factory.return_value
        result = await _upload(MagicMock())
    assert result["vectorized"] is False
    session.rollback.assert_called_once()
    session.close.assert_called_once()
    assert real is module.open_indexing_session


async def test_at_most_two_jobs_per_embedding_service_run_the_rest_degrade_at_once():
    release = threading.Event()
    started = []

    def hung(**kwargs):
        started.append(kwargs["file_id"])
        release.wait(5)
        return True

    module._service_slots.clear()

    async def one(i):
        return await ChatAttachmentService.vectorize_in_worker(
            app_id=2, agent_id=1, session_id="s", file_id=f"f{i}", filename="a.txt", file_path=None, content="x",
            embedding_service_id=77, timeout=3,
        )

    with patch.object(module, "open_indexing_session", _session_factory([])), \
            patch.object(module.PlaygroundMediaService, "get_temp_repository", return_value=None), \
            patch.object(module.PlaygroundMediaService, "vectorize_uploaded_file", hung):
        tasks = [asyncio.create_task(one(i)) for i in range(3)]
        for _ in range(500):  # wait for the condition (two started, one refused), never for a fixed time
            if len(started) == 2 and sum(t.done() for t in tasks) == 1:
                break
            await asyncio.sleep(0.01)
        assert len(started) == 2  # the third was refused at once, it is not waiting in a queue
        refused = [t for t in tasks if t.done()]
        assert len(refused) == 1 and refused[0].result() is False
        release.set()
        results = await asyncio.gather(*tasks)
    assert sorted(results) == [False, True, True]


def test_the_embedding_clients_get_the_configured_timeout_and_keep_library_retries(monkeypatch):
    from types import SimpleNamespace as NS

    from langchain_mistralai import MistralAIEmbeddings
    from langchain_openai import OpenAIEmbeddings

    from tools import embeddingTools as et

    service = NS(api_key="k", endpoint="http://x", api_version=None, extra_config=None)
    monkeypatch.delenv("AICT_EMBEDDING_REQUEST_TIMEOUT_SECONDS", raising=False)
    assert et.get_embedding_request_timeout() == 120
    openai = et._build_openai_embeddings(service, "m")
    assert openai.request_timeout == 120
    assert openai.max_retries == OpenAIEmbeddings(model="m", api_key="k").max_retries

    monkeypatch.setenv("AICT_EMBEDDING_REQUEST_TIMEOUT_SECONDS", "77")
    openai = et._build_openai_embeddings(service, "m")
    mistral = et._build_mistral_embeddings(service, "m")
    assert openai.request_timeout == 77
    assert mistral.timeout == 77
    assert mistral.max_retries == MistralAIEmbeddings(model="m", api_key="k").max_retries
    assert et._build_huggingface_embeddings(service, "m").client.timeout == 77


def test_the_indexing_executor_is_shut_down_without_waiting():
    module._get_indexing_executor()
    module.shutdown_indexing_executor()
    assert module._indexing_executor is None
