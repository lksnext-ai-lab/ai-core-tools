"""Unit coverage for `services.a2a_server.context_builders` (step_012, AD-3, AD-7).

No DB: `A2ARequestContextBuilder` is exercised with `task_store=None` (it
never reads the store), and `A2AServerCallContextBuilder` with a bare
`SimpleNamespace` standing in for the Starlette `Request` the real router
builds (AD-4).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from a2a.server.context import ServerCallContext
from a2a.types.a2a_pb2 import Message, Part, SendMessageRequest
from a2a.utils.errors import InternalError, InvalidParamsError
from google.protobuf.struct_pb2 import Struct, Value
from pydantic import SecretStr
from starlette.datastructures import Headers

from services.a2a_server.context_builders import (
    A2AServerCallContextBuilder,
    A2ARequestContextBuilder,
)
from services.a2a_server.identity import A2ACallScope, A2ACallerUser, A2ARequestLog


def _scope(*, app_max_file_size_mb=None):
    snapshot = SimpleNamespace(app_max_file_size_mb=app_max_file_size_mb)
    return A2ACallScope(
        app_id=1,
        app_slug="acme",
        agent_id=2,
        api_key_id=3,
        api_key_hash="a" * 64,
        api_key=SecretStr("irrelevant"),
        snapshot=snapshot,
        request_log=A2ARequestLog(method="SendMessage"),
        base_url="https://example.test",
    )


def _request(*, scope=None, headers=None):
    return SimpleNamespace(
        state=SimpleNamespace(a2a_scope=scope),
        headers=Headers(headers or {}),
    )


class TestA2AServerCallContextBuilder:
    def test_raises_a_generic_internal_error_when_scope_is_missing(self):
        """A missing `request.state.a2a_scope` is a router/wiring bug (AD-4), never
        surfaced with any internal detail -- just the SDK's generic `InternalError`."""
        builder = A2AServerCallContextBuilder()
        with pytest.raises(InternalError) as exc_info:
            builder.build(_request(scope=None))
        assert "a2a_scope" not in str(exc_info.value.message)
        assert "AD-4" not in str(exc_info.value.message)

    def test_builds_a_context_with_the_owner_and_scope(self):
        builder = A2AServerCallContextBuilder()
        scope = _scope()
        ctx = builder.build(_request(scope=scope, headers={"a2a-version": "1.0"}))
        assert isinstance(ctx.user, A2ACallerUser)
        assert ctx.user.user_name == f"a2a:1:2:{'a' * 64}"
        assert ctx.state["a2a"] is scope

    def test_header_allow_list_never_contains_secrets(self):
        builder = A2AServerCallContextBuilder()
        headers = {
            "X-Api-Key": "secret-key",
            "Authorization": "Bearer secret-token",
            "Cookie": "session=secret",
            "A2A-Version": "1.0",
            "A2A-Extensions": "ext-1",
            "Content-Type": "application/json",
            "User-Agent": "test-agent",
        }
        ctx = builder.build(_request(scope=_scope(), headers=headers))
        copied = ctx.state["headers"]
        assert copied == {
            "a2a-version": "1.0",
            "a2a-extensions": "ext-1",
            "content-type": "application/json",
            "user-agent": "test-agent",
        }
        assert "x-api-key" not in copied
        assert "authorization" not in copied
        assert "cookie" not in copied
        assert "secret-key" not in str(copied)
        assert "secret-token" not in str(copied)


def _send_request(parts, *, task_id=None, context_id=None) -> SendMessageRequest:
    message = Message(message_id=str(uuid.uuid4()), parts=parts)
    if task_id is not None:
        message.task_id = task_id
    if context_id is not None:
        message.context_id = context_id
    return SendMessageRequest(message=message)


def _ctx(scope=None) -> ServerCallContext:
    state = {"a2a": scope} if scope is not None else {}
    return ServerCallContext(state=state)


class TestA2ARequestContextBuilderRejections:
    @pytest.mark.parametrize(
        "parts",
        [
            [],
            [Part(text="   ")],
            [Part(text="\t\n ")],
        ],
    )
    async def test_rejects_zero_or_whitespace_only_parts(self, parts):
        builder = A2ARequestContextBuilder()
        with pytest.raises(InvalidParamsError):
            await builder.build(_ctx(), params=_send_request(parts))

    async def test_rejects_an_empty_part(self):
        builder = A2ARequestContextBuilder()
        with pytest.raises(InvalidParamsError):
            await builder.build(_ctx(), params=_send_request([Part()]))

    async def test_rejects_inline_file_over_the_cap(self, monkeypatch):
        monkeypatch.setenv("A2A_MAX_FILE_MB", "1")
        from utils.a2a_config import get_a2a_config

        get_a2a_config.cache_clear()
        try:
            builder = A2ARequestContextBuilder()
            oversized = b"x" * (2 * 1024 * 1024)
            with pytest.raises(InvalidParamsError):
                await builder.build(_ctx(_scope()), params=_send_request([Part(raw=oversized)]))
        finally:
            get_a2a_config.cache_clear()

    async def test_accepts_inline_file_within_the_cap(self):
        builder = A2ARequestContextBuilder()
        small = b"x" * 10
        request_context = await builder.build(_ctx(_scope()), params=_send_request([Part(raw=small)]))
        assert request_context.task_id is not None

    async def test_rejects_a_data_part_nested_too_deeply(self):
        builder = A2ARequestContextBuilder()
        value = Value()
        current = value
        for _ in range(40):
            current = current.list_value.values.add()
        current.string_value = "leaf"
        with pytest.raises(InvalidParamsError):
            await builder.build(_ctx(_scope()), params=_send_request([Part(data=value)]))

    async def test_accepts_a_shallow_data_part(self):
        builder = A2ARequestContextBuilder()
        value = Value(string_value="hello")
        request_context = await builder.build(_ctx(_scope()), params=_send_request([Part(data=value)]))
        assert request_context.task_id is not None

    @pytest.mark.parametrize("bad_id", ["x" * 37, "has a space", "has/slash", ""])
    async def test_rejects_malformed_task_id(self, bad_id):
        builder = A2ARequestContextBuilder()
        with pytest.raises(InvalidParamsError):
            await builder.build(_ctx(), params=_send_request([Part(text="hi")]), task_id=bad_id)

    @pytest.mark.parametrize("bad_id", ["x" * 37, "has a space"])
    async def test_rejects_malformed_context_id(self, bad_id):
        builder = A2ARequestContextBuilder()
        with pytest.raises(InvalidParamsError):
            await builder.build(_ctx(), params=_send_request([Part(text="hi")]), context_id=bad_id)

    async def test_accepts_a_valid_task_and_context_id(self):
        builder = A2ARequestContextBuilder()
        request_context = await builder.build(
            _ctx(),
            params=_send_request([Part(text="hi")]),
            task_id="task-1",
            context_id="ctx-1",
        )
        assert request_context.task_id == "task-1"
        assert request_context.context_id == "ctx-1"

    async def test_records_task_and_context_id_on_the_scope_request_log(self):
        builder = A2ARequestContextBuilder()
        scope = _scope()
        await builder.build(
            _ctx(scope),
            params=_send_request([Part(text="hi")]),
            task_id="task-1",
            context_id="ctx-1",
        )
        assert scope.request_log.task_id == "task-1"
        assert scope.request_log.context_id == "ctx-1"

    async def test_a_message_with_only_a_file_part_is_accepted_even_without_text(self):
        builder = A2ARequestContextBuilder()
        request_context = await builder.build(
            _ctx(_scope()), params=_send_request([Part(url="https://example.test/file.pdf")])
        )
        assert request_context.task_id is not None

    async def test_rejects_too_many_parts(self, monkeypatch):
        monkeypatch.setenv("A2A_MAX_PARTS", "3")
        from utils.a2a_config import get_a2a_config

        get_a2a_config.cache_clear()
        try:
            builder = A2ARequestContextBuilder()
            parts = [Part(text=f"part-{i}") for i in range(4)]
            with pytest.raises(InvalidParamsError):
                await builder.build(_ctx(), params=_send_request(parts))
        finally:
            get_a2a_config.cache_clear()

    async def test_accepts_exactly_the_max_parts_cap(self, monkeypatch):
        monkeypatch.setenv("A2A_MAX_PARTS", "3")
        from utils.a2a_config import get_a2a_config

        get_a2a_config.cache_clear()
        try:
            builder = A2ARequestContextBuilder()
            parts = [Part(text=f"part-{i}") for i in range(3)]
            request_context = await builder.build(_ctx(), params=_send_request(parts))
            assert request_context.task_id is not None
        finally:
            get_a2a_config.cache_clear()

    async def test_rejects_too_many_file_parts(self, monkeypatch):
        monkeypatch.setenv("A2A_MAX_FILE_PARTS", "2")
        from utils.a2a_config import get_a2a_config

        get_a2a_config.cache_clear()
        try:
            builder = A2ARequestContextBuilder()
            parts = [Part(url=f"https://example.test/{i}.pdf") for i in range(3)]
            with pytest.raises(InvalidParamsError):
                await builder.build(_ctx(_scope()), params=_send_request(parts))
        finally:
            get_a2a_config.cache_clear()

    async def test_rejects_total_request_size_over_the_cap(self, monkeypatch):
        monkeypatch.setenv("A2A_MAX_REQUEST_MB", "1")
        monkeypatch.setenv("A2A_MAX_FILE_MB", "1")
        from utils.a2a_config import get_a2a_config

        get_a2a_config.cache_clear()
        try:
            builder = A2ARequestContextBuilder()
            # Two 600 KB parts, each under the 1 MB per-file cap, but summing
            # past the 1 MB total-request cap.
            parts = [Part(raw=b"x" * 600_000), Part(raw=b"y" * 600_000)]
            with pytest.raises(InvalidParamsError):
                await builder.build(_ctx(_scope()), params=_send_request(parts))
        finally:
            get_a2a_config.cache_clear()

    @pytest.mark.parametrize(
        "url",
        [
            "",
            "ftp://example.test/file.pdf",
            "javascript:alert(1)",
            "https://" + ("x" * 2050) + ".test/file.pdf",
        ],
    )
    async def test_rejects_malformed_file_urls(self, url):
        builder = A2ARequestContextBuilder()
        with pytest.raises(InvalidParamsError):
            await builder.build(_ctx(_scope()), params=_send_request([Part(url=url)]))

    async def test_accepts_a_well_formed_https_url(self):
        builder = A2ARequestContextBuilder()
        request_context = await builder.build(
            _ctx(_scope()), params=_send_request([Part(url="https://example.test/file.pdf")])
        )
        assert request_context.task_id is not None

    async def test_rejects_filename_over_the_length_cap(self):
        builder = A2ARequestContextBuilder()
        part = Part(raw=b"x", filename="f" * 256)
        with pytest.raises(InvalidParamsError):
            await builder.build(_ctx(_scope()), params=_send_request([part]))

    async def test_rejects_media_type_over_the_length_cap(self):
        builder = A2ARequestContextBuilder()
        part = Part(raw=b"x", media_type="m" * 256)
        with pytest.raises(InvalidParamsError):
            await builder.build(_ctx(_scope()), params=_send_request([part]))

    async def test_rejects_a_part_metadata_struct_nested_too_deeply(self):
        builder = A2ARequestContextBuilder()
        struct = Struct()
        current_value = struct.fields["root"]
        for _ in range(40):
            current_value = current_value.list_value.values.add()
        current_value.string_value = "leaf"
        part = Part(text="hi")
        part.metadata.CopyFrom(struct)
        with pytest.raises(InvalidParamsError):
            await builder.build(_ctx(_scope()), params=_send_request([part]))

    async def test_rejects_a_message_metadata_struct_nested_too_deeply(self):
        builder = A2ARequestContextBuilder()
        struct = Struct()
        current_value = struct.fields["root"]
        for _ in range(40):
            current_value = current_value.list_value.values.add()
        current_value.string_value = "leaf"
        message = Message(message_id=str(uuid.uuid4()), parts=[Part(text="hi")])
        message.metadata.CopyFrom(struct)
        with pytest.raises(InvalidParamsError):
            await builder.build(_ctx(_scope()), params=SendMessageRequest(message=message))

    async def test_accepts_a_shallow_part_metadata_struct(self):
        builder = A2ARequestContextBuilder()
        part = Part(text="hi")
        part.metadata.fields["key"].string_value = "value"
        request_context = await builder.build(_ctx(_scope()), params=_send_request([part]))
        assert request_context.task_id is not None

    async def test_rejects_a_data_part_nested_too_deeply_via_per_app_cap_override(self, monkeypatch):
        """A per-app `app_max_file_size_mb` override is honoured by the per-file cap
        used for DataPart/raw-file size checks (not the global `A2A_MAX_FILE_MB`)."""
        monkeypatch.setenv("A2A_MAX_FILE_MB", "10")
        from utils.a2a_config import get_a2a_config

        get_a2a_config.cache_clear()
        try:
            builder = A2ARequestContextBuilder()
            scope = _scope(app_max_file_size_mb=1)  # 1 MB override, stricter than the 10 MB default
            oversized = b"x" * (2 * 1024 * 1024)
            with pytest.raises(InvalidParamsError):
                await builder.build(_ctx(scope), params=_send_request([Part(raw=oversized)]))

            # The same payload is accepted once the override is generous enough.
            generous_scope = _scope(app_max_file_size_mb=5)
            request_context = await builder.build(
                _ctx(generous_scope), params=_send_request([Part(raw=oversized)])
            )
            assert request_context.task_id is not None
        finally:
            get_a2a_config.cache_clear()

    async def test_rejects_a_data_part_at_the_size_cap_boundary(self, monkeypatch):
        monkeypatch.setenv("A2A_MAX_FILE_MB", "1")
        from utils.a2a_config import get_a2a_config

        get_a2a_config.cache_clear()
        try:
            builder = A2ARequestContextBuilder()
            value = Value(string_value="x" * (2 * 1024 * 1024))
            with pytest.raises(InvalidParamsError):
                await builder.build(_ctx(_scope()), params=_send_request([Part(data=value)]))
        finally:
            get_a2a_config.cache_clear()
