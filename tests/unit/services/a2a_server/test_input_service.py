"""Unit tests for ``services.a2a_server.input_service.build_turn_inputs`` (FR-18, NFR-5).

No real network access: FMS is mocked (``AsyncMock(spec=FileManagementService)``,
so a typo'd attribute fails loudly) for most cases. Two classes use a real
``FileManagementService`` against a ``tmp_path`` directory — no mock — to prove
``strict=True`` genuinely rejects an unsupported type / a corrupt PDF rather
than substituting a placeholder, and that ``fetch_bytes``'s SSRF guard really
blocks a loopback target before connecting.
"""

import asyncio
import itertools
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import a2a.types as a2a_types
import pytest
from fastapi import HTTPException

from services.a2a_server.input_service import (
    A2AInputError,
    build_turn_inputs,
    cleanup,
)
from services.file_management_service import FileManagementService, FileReference
from utils.a2a_config import get_a2a_config
from utils.ssrf_guard import FetchedFile, FetchError, SsrfBlockedError


def _snapshot(*, agent_id=1, app_max_file_size_mb=None, has_memory=False):
    return SimpleNamespace(
        agent_id=agent_id,
        app_max_file_size_mb=app_max_file_size_mb,
        has_memory=has_memory,
    )


def _message(*parts):
    message = a2a_types.Message()
    for build_part in parts:
        part = message.parts.add()
        build_part(part)
    return message


def _text_part(text):
    def _build(part):
        part.text = text
    return _build


def _data_part(value):
    from google.protobuf import json_format

    def _build(part):
        json_format.ParseDict(value, part.data)
    return _build


def _raw_part(data: bytes, *, filename="", media_type=""):
    def _build(part):
        part.raw = data
        if filename:
            part.filename = filename
        if media_type:
            part.media_type = media_type
    return _build


def _url_part(url: str, *, filename="", media_type=""):
    def _build(part):
        part.url = url
        if filename:
            part.filename = filename
        if media_type:
            part.media_type = media_type
    return _build


_file_id_counter = itertools.count(1)


def _mock_fms(upload_side_effect=None, existing_refs=None):
    """An ``AsyncMock`` autospecced against the real class: a typo'd attribute
    (e.g. calling a method that doesn't exist) fails the test instead of
    silently returning another ``MagicMock``."""
    fms = AsyncMock(spec=FileManagementService)
    if upload_side_effect is not None:
        fms.upload_file.side_effect = upload_side_effect
    else:
        async def _default_upload(file, agent_id, user_context, conversation_id, has_memory, strict=False):
            return FileReference(
                file_id=f"new-file-{next(_file_id_counter)}",
                filename=file.filename,
                file_type="unknown",
                content="",
                file_size_bytes=0,
            )
        fms.upload_file.side_effect = _default_upload
    fms.resolve_chat_files.return_value = existing_refs or []
    return fms


@pytest.fixture(autouse=True)
def _reset_a2a_config():
    get_a2a_config.cache_clear()
    yield
    get_a2a_config.cache_clear()


class TestTextAndDataParts:
    @pytest.mark.asyncio
    async def test_text_parts_are_joined_with_double_newline(self):
        message = _message(_text_part("hello"), _text_part("world"))
        fms = _mock_fms()

        result = await build_turn_inputs(
            message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms
        )

        assert result.text == "hello\n\nworld"
        assert result.file_refs == []

    @pytest.mark.asyncio
    async def test_data_part_renders_fenced_json_block_with_int_not_float(self):
        """AC-25: {"a": 1} must render as {"a": 1}, not {"a": 1.0}."""
        message = _message(_data_part({"a": 1}))
        fms = _mock_fms()

        result = await build_turn_inputs(
            message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms
        )

        assert result.text.startswith("```json\n")
        assert result.text.endswith("\n```")
        assert '"a": 1' in result.text
        assert "1.0" not in result.text

    @pytest.mark.asyncio
    async def test_text_and_data_parts_are_appended_in_order(self):
        message = _message(_text_part("before"), _data_part({"x": 2}), _text_part("after"))
        fms = _mock_fms()

        result = await build_turn_inputs(
            message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms
        )

        assert result.text.startswith("before\n\n```json")
        assert result.text.endswith("after")


class TestFileBytesParts:
    @pytest.mark.asyncio
    async def test_bytes_part_uploads_with_correct_filename_and_content_type(self):
        message = _message(_raw_part(b"hello world", filename="notes.txt", media_type="text/plain"))
        fms = _mock_fms()

        result = await build_turn_inputs(
            message, snapshot=_snapshot(agent_id=42), user_context={"api_key": "k"}, conversation_id=7, fms=fms
        )

        assert len(result.file_refs) == 1
        fms.upload_file.assert_awaited_once()
        _, kwargs = fms.upload_file.await_args
        uploaded = kwargs["file"]
        assert uploaded.filename == "notes.txt"
        assert uploaded.headers["content-type"] == "text/plain"
        assert kwargs["agent_id"] == 42
        assert kwargs["conversation_id"] == 7
        assert kwargs["strict"] is True

    @pytest.mark.asyncio
    async def test_bytes_part_filename_is_sanitized_and_defaulted(self):
        message = _message(_raw_part(b"data", filename="../../etc/passwd"))
        fms = _mock_fms()

        await build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)

        _, kwargs = fms.upload_file.await_args
        assert kwargs["file"].filename == "passwd"
        assert ".." not in kwargs["file"].filename
        assert "/" not in kwargs["file"].filename

    @pytest.mark.asyncio
    async def test_bytes_part_filename_gets_extension_from_media_type(self):
        """Review round 1, item 2: "report" + application/pdf must reach upload as "report.pdf"."""
        message = _message(_raw_part(b"%PDF-ish", filename="report", media_type="application/pdf"))
        fms = _mock_fms()

        await build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)

        _, kwargs = fms.upload_file.await_args
        assert kwargs["file"].filename == "report.pdf"

    @pytest.mark.asyncio
    async def test_bytes_part_media_type_with_charset_param_still_guesses_extension(self):
        """Review round 2, item 3: "text/plain; charset=utf-8" must still guess ".txt"."""
        message = _message(_raw_part(b"hello", filename="notes", media_type="text/plain; charset=utf-8"))
        fms = _mock_fms()

        await build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)

        _, kwargs = fms.upload_file.await_args
        assert kwargs["file"].filename == "notes.txt"

    @pytest.mark.asyncio
    async def test_bytes_part_long_and_nul_filename_is_sanitized(self):
        """Review round 1, item 3: a 300-char name and a NUL byte never surface in the error."""
        long_name = ("a" * 300) + ".txt"
        message = _message(_raw_part(b"x", filename=long_name))
        fms = _mock_fms(upload_side_effect=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

        with pytest.raises(A2AInputError) as exc_info:
            await build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)

        message_str = str(exc_info.value)
        assert len(message_str.encode("utf-8")) < 300
        assert "/" not in message_str
        assert "Errno" not in message_str

    @pytest.mark.asyncio
    async def test_bytes_part_nul_byte_in_filename_is_stripped(self):
        message = _message(_raw_part(b"x", filename="evil\x00name.txt"))
        fms = _mock_fms()

        await build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)

        _, kwargs = fms.upload_file.await_args
        assert "\x00" not in kwargs["file"].filename

    @pytest.mark.asyncio
    async def test_bytes_part_over_per_file_cap_raises_and_never_uploads(self, monkeypatch):
        monkeypatch.setenv("A2A_MAX_FILE_MB", "1")
        get_a2a_config.cache_clear()
        oversized = b"x" * (2 * 1024 * 1024)
        message = _message(_raw_part(oversized, filename="big.bin"))
        fms = _mock_fms()

        with pytest.raises(A2AInputError) as exc_info:
            await build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)

        assert "part 1" in str(exc_info.value)
        fms.upload_file.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_upload_failure_becomes_input_error_naming_the_part(self):
        """Unsupported MIME / any upload failure must fail the part, never a placeholder."""
        async def _fail(**kwargs):
            raise HTTPException(status_code=400, detail="Unsupported file type")

        message = _message(_raw_part(b"data", filename="weird.xyz"))
        fms = _mock_fms(upload_side_effect=_fail)

        with pytest.raises(A2AInputError) as exc_info:
            await build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)

        assert "weird.xyz" in str(exc_info.value)
        # No placeholder content is ever substituted: the error propagates, no FileReference returned.

    @pytest.mark.asyncio
    async def test_upload_5xx_detail_is_never_forwarded(self):
        """Review round 1, item 3: a 5xx HTTPException.detail must never reach the caller verbatim."""
        async def _fail(**kwargs):
            raise HTTPException(status_code=500, detail="Internal: disk full at /var/secret/path")

        message = _message(_raw_part(b"data", filename="a.txt"))
        fms = _mock_fms(upload_side_effect=_fail)

        with pytest.raises(A2AInputError) as exc_info:
            await build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)

        assert "disk full" not in str(exc_info.value)
        assert "/var/secret/path" not in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_failure_cleans_up_already_uploaded_refs_from_this_turn(self):
        uploaded_ref = FileReference(file_id="f1", filename="a.txt", file_type="text", content="")
        uploaded_ref.storage_strategy = "ephemeral"

        call_count = {"n": 0}

        async def _side_effect(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return uploaded_ref
            raise RuntimeError("boom")

        message = _message(
            _raw_part(b"ok", filename="a.txt"),
            _raw_part(b"bad", filename="b.txt"),
        )
        fms = _mock_fms(upload_side_effect=_side_effect)

        with pytest.raises(A2AInputError):
            await build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)

        fms.cleanup_ephemeral_refs.assert_awaited_once()
        (cleaned_refs,), _ = fms.cleanup_ephemeral_refs.await_args
        assert cleaned_refs == [uploaded_ref]

    @pytest.mark.asyncio
    async def test_failure_on_memory_agent_also_removes_persistent_refs(self):
        """Review round 1, item 5: a failed turn must leave nothing attached, even for a memory agent."""
        persistent_ref = FileReference(file_id="p1", filename="a.txt", file_type="text", content="")
        persistent_ref.storage_strategy = "persistent"

        call_count = {"n": 0}

        async def _side_effect(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return persistent_ref
            raise RuntimeError("boom")

        message = _message(
            _raw_part(b"ok", filename="a.txt"),
            _raw_part(b"bad", filename="b.txt"),
        )
        fms = _mock_fms(upload_side_effect=_side_effect)

        with pytest.raises(A2AInputError):
            await build_turn_inputs(
                message,
                snapshot=_snapshot(has_memory=True),
                user_context={},
                conversation_id=99,
                fms=fms,
            )

        fms.remove_files.assert_awaited_once()
        (file_ids,), kwargs = fms.remove_files.await_args
        assert file_ids == ["p1"]
        assert kwargs["conversation_id"] == "99"

    @pytest.mark.asyncio
    async def test_two_file_parts_upload_in_order_and_both_are_returned(self):
        message = _message(
            _raw_part(b"one", filename="one.txt"),
            _raw_part(b"two", filename="two.txt"),
        )
        fms = _mock_fms()

        result = await build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)

        assert len(result.file_refs) == 2
        assert [c.kwargs["file"].filename for c in fms.upload_file.await_args_list] == ["one.txt", "two.txt"]

    @pytest.mark.asyncio
    async def test_total_request_cap_rejects_second_file(self, monkeypatch):
        monkeypatch.setenv("A2A_MAX_REQUEST_MB", "1")
        monkeypatch.setenv("A2A_MAX_FILE_MB", "1")
        get_a2a_config.cache_clear()
        chunk = b"x" * (600 * 1024)
        message = _message(
            _raw_part(chunk, filename="one.bin"),
            _raw_part(chunk, filename="two.bin"),
        )
        fms = _mock_fms()

        with pytest.raises(A2AInputError) as exc_info:
            await build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)

        assert "part 2" in str(exc_info.value)
        fms.upload_file.assert_awaited_once()  # only the first file was uploaded

    @pytest.mark.asyncio
    async def test_too_many_parts_rejected_before_any_upload(self, monkeypatch):
        monkeypatch.setenv("A2A_MAX_PARTS", "2")
        get_a2a_config.cache_clear()
        message = _message(_text_part("a"), _text_part("b"), _text_part("c"))
        fms = _mock_fms()

        with pytest.raises(A2AInputError):
            await build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)
        fms.upload_file.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_too_many_file_parts_rejected_before_any_fetch(self, monkeypatch):
        monkeypatch.setenv("A2A_MAX_FILE_PARTS", "1")
        get_a2a_config.cache_clear()
        message = _message(
            _raw_part(b"a", filename="a.txt"),
            _raw_part(b"b", filename="b.txt"),
        )
        fms = _mock_fms()

        with pytest.raises(A2AInputError):
            await build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)
        fms.upload_file.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cancellation_mid_part_still_cleans_up_prior_part(self):
        """Review round 1, item 4: cancelling during part 2's slow upload still cleans up part 1's ref."""
        part1_ref = FileReference(file_id="p1", filename="one.txt", file_type="text", content="")
        part1_ref.storage_strategy = "ephemeral"
        call_count = {"n": 0}

        async def _side_effect(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return part1_ref
            await asyncio.sleep(10)  # part 2: cancelled while "in flight"
            raise AssertionError("should have been cancelled")

        message = _message(
            _raw_part(b"one", filename="one.txt"),
            _raw_part(b"two", filename="two.txt"),
        )
        fms = _mock_fms(upload_side_effect=_side_effect)

        task = asyncio.ensure_future(
            build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)
        )
        await asyncio.sleep(0)  # let part 1 finish and part 2 start sleeping
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        fms.cleanup_ephemeral_refs.assert_awaited_once()
        (cleaned_refs,), _ = fms.cleanup_ephemeral_refs.await_args
        assert cleaned_refs == [part1_ref]

    @pytest.mark.asyncio
    async def test_second_cancel_during_cleanup_does_not_abort_it(self):
        """Review round 2, item 4: a second cancel racing the cleanup itself must not
        truncate it — only asyncio.shield's own await is interrupted."""
        cleanup_done = {"flag": False}
        part1_ref = FileReference(file_id="p1", filename="one.txt", file_type="text", content="")
        part1_ref.storage_strategy = "ephemeral"
        call_count = {"n": 0}

        async def _side_effect(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return part1_ref
            await asyncio.sleep(10)
            raise AssertionError("should have been cancelled")

        async def _slow_cleanup(refs):
            await asyncio.sleep(0.2)
            cleanup_done["flag"] = True

        message = _message(
            _raw_part(b"one", filename="one.txt"),
            _raw_part(b"two", filename="two.txt"),
        )
        fms = _mock_fms(upload_side_effect=_side_effect)
        fms.cleanup_ephemeral_refs.side_effect = _slow_cleanup

        task = asyncio.ensure_future(
            build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)
        )
        await asyncio.sleep(0)  # part 1 finishes, part 2 starts its long sleep
        await asyncio.sleep(0)
        task.cancel()  # 1st cancel: aborts part 2, finally starts the shielded cleanup
        await asyncio.sleep(0)  # let the finally block begin awaiting the shield
        await asyncio.sleep(0)
        task.cancel()  # 2nd cancel: must only interrupt the shield's await, not the cleanup
        with pytest.raises(asyncio.CancelledError):
            await task

        # The shielded cleanup keeps running detached even after the task
        # itself finished raising CancelledError to its caller.
        await asyncio.sleep(0.3)
        assert cleanup_done["flag"] is True


class TestFileUriParts:
    @pytest.mark.asyncio
    async def test_blocked_uri_raises_and_never_uploads(self, monkeypatch):
        async def _blocked(*args, **kwargs):
            raise SsrfBlockedError("blocked")

        monkeypatch.setattr("services.a2a_server.input_service.fetch_bytes", _blocked)

        message = _message(_url_part("http://169.254.169.254/secret", filename="meta.json"))
        fms = _mock_fms()

        with pytest.raises(A2AInputError) as exc_info:
            await build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)

        assert "part 1" in str(exc_info.value)
        fms.upload_file.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fetch_error_is_raised_from_none_not_chained_to_the_url(self, monkeypatch):
        """Review round 1, item 7: the FetchError (which may embed the URL) must not be chained."""
        async def _timeout(*args, **kwargs):
            raise SsrfBlockedError("http://169.254.169.254/secret-token=abc should never appear")

        monkeypatch.setattr("services.a2a_server.input_service.fetch_bytes", _timeout)

        message = _message(_url_part("http://169.254.169.254/secret-token=abc"))
        fms = _mock_fms()

        with pytest.raises(A2AInputError) as exc_info:
            await build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)

        assert exc_info.value.__cause__ is None
        assert "secret-token" not in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_tls_error_raises_input_error(self, monkeypatch):
        from utils.ssrf_guard import FetchTransportError

        async def _tls_fail(*args, **kwargs):
            raise FetchTransportError("TLS error: certificate verify failed")

        monkeypatch.setattr("services.a2a_server.input_service.fetch_bytes", _tls_fail)

        message = _message(_url_part("https://example.invalid/file.pdf"))
        fms = _mock_fms()

        with pytest.raises(A2AInputError):
            await build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)
        fms.upload_file.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_bare_fetch_error_is_handled(self, monkeypatch):
        """Review round 1, item 8: the FetchError base class itself (e.g. bad Content-Encoding)."""
        async def _bare_error(*args, **kwargs):
            raise FetchError("Unsupported Content-Encoding: 'br'")

        monkeypatch.setattr("services.a2a_server.input_service.fetch_bytes", _bare_error)

        message = _message(_url_part("https://example.com/file.bin"))
        fms = _mock_fms()

        with pytest.raises(A2AInputError) as exc_info:
            await build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)
        assert "br" not in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_non_http_scheme_is_rejected_without_fetching(self, monkeypatch):
        called = {"yes": False}

        async def _should_not_be_called(*args, **kwargs):
            called["yes"] = True
            raise AssertionError("fetch_bytes must not be called for a disallowed scheme")

        monkeypatch.setattr("services.a2a_server.input_service.fetch_bytes", _should_not_be_called)

        message = _message(_url_part("ftp://example.com/file.bin"))
        fms = _mock_fms()

        with pytest.raises(A2AInputError):
            await build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)
        assert called["yes"] is False

    @pytest.mark.asyncio
    async def test_successful_fetch_uploads_fetched_bytes(self, monkeypatch):
        async def _fake_fetch(url, *, max_bytes, timeout_s, max_redirects):
            return FetchedFile(content=b"remote content", media_type="text/plain", filename="remote.txt", final_url=url)

        monkeypatch.setattr("services.a2a_server.input_service.fetch_bytes", _fake_fetch)

        message = _message(_url_part("https://example.com/remote.txt"))
        fms = _mock_fms()

        result = await build_turn_inputs(
            message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms
        )

        assert len(result.file_refs) == 1
        _, kwargs = fms.upload_file.await_args
        assert kwargs["file"].filename == "remote.txt"

    @pytest.mark.asyncio
    async def test_fetch_over_per_file_cap_raises(self, monkeypatch):
        from utils.ssrf_guard import FetchTooLargeError

        async def _too_large(*args, **kwargs):
            raise FetchTooLargeError("too large")

        monkeypatch.setattr("services.a2a_server.input_service.fetch_bytes", _too_large)

        message = _message(_url_part("https://example.com/huge.bin"))
        fms = _mock_fms()

        with pytest.raises(A2AInputError):
            await build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)

    @pytest.mark.asyncio
    async def test_shared_fetch_time_budget_exhausted_by_prior_fetches(self, monkeypatch):
        """Review round 1, item 6: multiple file-uri parts share one turn-level deadline."""
        monkeypatch.setenv("A2A_URI_FETCH_TIMEOUT_SECONDS", "1")
        get_a2a_config.cache_clear()

        async def _slow_fetch(url, *, max_bytes, timeout_s, max_redirects):
            await asyncio.sleep(1.1)
            return FetchedFile(content=b"x", media_type="text/plain", filename="x.txt", final_url=url)

        monkeypatch.setattr("services.a2a_server.input_service.fetch_bytes", _slow_fetch)

        message = _message(
            _url_part("https://example.com/one.txt"),
            _url_part("https://example.com/two.txt"),
        )
        fms = _mock_fms()

        with pytest.raises(A2AInputError) as exc_info:
            await build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)

        assert "part 2" in str(exc_info.value)
        fms.upload_file.assert_awaited_once()  # only part 1 was ever uploaded

    @pytest.mark.asyncio
    async def test_partly_used_fetch_budget_shrinks_the_next_fetchs_timeout(self, monkeypatch):
        """Review round 2, item 5: part 2's fetch gets less than the full configured timeout."""
        monkeypatch.setenv("A2A_URI_FETCH_TIMEOUT_SECONDS", "1")
        get_a2a_config.cache_clear()

        seen_timeouts = []

        async def _fetch(url, *, max_bytes, timeout_s, max_redirects):
            seen_timeouts.append(timeout_s)
            if len(seen_timeouts) == 1:
                await asyncio.sleep(0.3)
            return FetchedFile(content=b"x", media_type="text/plain", filename="x.txt", final_url=url)

        monkeypatch.setattr("services.a2a_server.input_service.fetch_bytes", _fetch)

        message = _message(
            _url_part("https://example.com/one.txt"),
            _url_part("https://example.com/two.txt"),
        )
        fms = _mock_fms()

        await build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)

        assert len(seen_timeouts) == 2
        assert seen_timeouts[0] == pytest.approx(1.0)
        assert seen_timeouts[1] < seen_timeouts[0]
        assert seen_timeouts[1] == pytest.approx(0.7, abs=0.2)

    @pytest.mark.asyncio
    async def test_unexpected_non_fetch_error_is_wrapped_generically(self, monkeypatch):
        """Review round 2, item 4: fetch_bytes raising something other than FetchError must still
        become a generic A2AInputError, never propagate raw."""
        async def _buggy_fetch(*args, **kwargs):
            raise ValueError("some unexpected internal bug, with a secret /etc/passwd path")

        monkeypatch.setattr("services.a2a_server.input_service.fetch_bytes", _buggy_fetch)

        message = _message(_url_part("https://example.com/file.bin"))
        fms = _mock_fms()

        with pytest.raises(A2AInputError) as exc_info:
            await build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)

        message_str = str(exc_info.value)
        assert "secret" not in message_str
        assert "/etc/passwd" not in message_str
        fms.upload_file.assert_not_awaited()


class TestMergeWithExistingFiles:
    @pytest.mark.asyncio
    async def test_existing_attached_files_are_merged_without_duplicates(self):
        existing = FileReference(file_id="existing-1", filename="old.pdf", file_type="pdf", content="")
        message = _message(_text_part("hi"))
        fms = _mock_fms(existing_refs=[existing])

        result = await build_turn_inputs(
            message, snapshot=_snapshot(), user_context={}, conversation_id=5, fms=fms
        )

        assert result.file_refs == [existing]
        fms.resolve_chat_files.assert_awaited_once()
        _, kwargs = fms.resolve_chat_files.await_args
        assert kwargs["files"] is None
        assert kwargs["file_reference_ids"] is None

    @pytest.mark.asyncio
    async def test_new_upload_takes_precedence_over_duplicate_existing_id(self):
        new_ref = FileReference(file_id="dup-1", filename="new.pdf", file_type="pdf", content="")

        async def _upload(**kwargs):
            return new_ref

        existing_dup = FileReference(file_id="dup-1", filename="stale.pdf", file_type="pdf", content="")
        message = _message(_raw_part(b"data", filename="new.pdf"))
        fms = _mock_fms(upload_side_effect=_upload, existing_refs=[existing_dup])

        result = await build_turn_inputs(
            message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms
        )

        assert result.file_refs == [new_ref]


class TestCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_delegates_to_fms(self):
        fms = _mock_fms()
        refs = [FileReference(file_id="a", filename="a.txt", file_type="text", content="")]

        await cleanup(fms, refs)

        fms.cleanup_ephemeral_refs.assert_awaited_once_with(refs)


class TestNoPlaceholderEver:
    @pytest.mark.asyncio
    async def test_failed_part_never_yields_a_file_ref_with_placeholder_content(self, monkeypatch):
        async def _blocked(*args, **kwargs):
            raise SsrfBlockedError("blocked")

        monkeypatch.setattr("services.a2a_server.input_service.fetch_bytes", _blocked)
        message = _message(_url_part("http://10.0.0.5/x"))
        fms = _mock_fms()

        with pytest.raises(A2AInputError):
            await build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)

        fms.upload_file.assert_not_awaited()


class TestRealSsrfGuardIntegration:
    """Uses the real fetch_bytes/SSRF guard — no mock — against 127.0.0.1.

    This is the AC-26 "no request reaches the private address" proof at the
    input_service level, mirroring the same real-loopback pattern used by
    ``tests/unit/utils/test_ssrf_guard.py``: no outbound network traffic ever
    leaves the loopback interface, and no DB is needed, so it belongs here
    rather than under ``tests/integration``.
    """

    @pytest.mark.asyncio
    async def test_localhost_uri_is_blocked_before_connecting(self):
        message = _message(_url_part("http://127.0.0.1:1/blocked", filename="x.bin"))
        fms = _mock_fms()

        with pytest.raises(A2AInputError) as exc_info:
            await build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)

        assert "part 1" in str(exc_info.value)
        fms.upload_file.assert_not_awaited()


def _real_fms(tmp_path):
    with patch("utils.config.get_app_config", return_value={"TMP_BASE_FOLDER": str(tmp_path)}):
        return FileManagementService()


class TestRealFileManagementServiceStrictMode:
    """Review round 1, item 1: drives a real ``FileManagementService`` (no mock)
    so ``strict=True`` is proven to actually reject, end to end, rather than
    trusting a mock that could drift from the real implementation."""

    @pytest.mark.asyncio
    async def test_unsupported_extension_is_rejected_not_placeholder(self, tmp_path):
        fms = _real_fms(tmp_path)
        message = _message(_raw_part(b"whatever bytes", filename="weird.xyz"))

        with pytest.raises(A2AInputError) as exc_info:
            await build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)

        message_str = str(exc_info.value)
        assert "weird.xyz" in message_str
        assert "not implemented" not in message_str
        assert "type: unknown" not in message_str
        # Review round 2, item 2: the reason forwarded is upload_file's own
        # known-safe 415 detail, not something ad hoc.
        assert "Unsupported file type" in message_str

    @pytest.mark.asyncio
    async def test_corrupt_pdf_is_rejected_not_placeholder_error_text(self, tmp_path):
        fms = _real_fms(tmp_path)
        message = _message(_raw_part(b"not a real pdf at all", filename="broken.pdf", media_type="application/pdf"))

        with pytest.raises(A2AInputError) as exc_info:
            await build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)

        message_str = str(exc_info.value)
        assert "broken.pdf" in message_str
        # Never the raw extractor exception text (would leak internals to the LLM).
        assert "Error processing file" not in message_str
        assert "Stream" not in message_str
        # Review round 2, item 2: the reason forwarded is upload_file's own
        # known-safe 422 detail.
        assert "File processing failed" in message_str

    @pytest.mark.asyncio
    async def test_rejection_leaves_no_orphaned_temp_file(self, tmp_path):
        """Review round 2, item 1: a strict rejection must not leak the spooled upload."""
        fms = _real_fms(tmp_path)
        uploads_dir = tmp_path / "uploads"

        for i in range(3):
            message = _message(_raw_part(b"whatever bytes", filename=f"weird{i}.xyz"))
            with pytest.raises(A2AInputError):
                await build_turn_inputs(
                    message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms
                )

        assert os.listdir(uploads_dir) == []

    @pytest.mark.asyncio
    async def test_corrupt_pdf_rejection_leaves_no_orphaned_temp_file(self, tmp_path):
        fms = _real_fms(tmp_path)
        uploads_dir = tmp_path / "uploads"
        message = _message(_raw_part(b"not a real pdf at all", filename="broken.pdf", media_type="application/pdf"))

        with pytest.raises(A2AInputError):
            await build_turn_inputs(message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms)

        assert os.listdir(uploads_dir) == []

    @pytest.mark.asyncio
    async def test_valid_minimal_pdf_is_accepted_and_extracted(self, tmp_path):
        """A real, well-formed (if content-empty) PDF must succeed end to end."""
        from pypdf import PdfWriter
        import io

        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        buf = io.BytesIO()
        writer.write(buf)

        fms = _real_fms(tmp_path)
        message = _message(_raw_part(buf.getvalue(), filename="report", media_type="application/pdf"))

        result = await build_turn_inputs(
            message, snapshot=_snapshot(), user_context={}, conversation_id=None, fms=fms
        )

        assert len(result.file_refs) == 1
        assert result.file_refs[0].filename == "report.pdf"
        assert result.file_refs[0].file_type == "pdf"
