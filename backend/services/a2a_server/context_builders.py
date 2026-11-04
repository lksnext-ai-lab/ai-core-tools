"""`ServerCallContext` and `RequestContext` builders (AD-3, AD-7).

Two builders, both wired into the single process-wide runtime
(`services/a2a_server/runtime.py`):

- `A2AServerCallContextBuilder` turns the Starlette `Request` the router
  already validated (visibility, API key, origin -- AD-4) into the SDK's
  `ServerCallContext`: the owner-bearing `A2ACallerUser` plus
  `state["a2a"]`/`state["headers"]` (AD-3).
- `A2ARequestContextBuilder` runs **before** the SDK ever creates a `Task`
  row (AD-7): `DefaultRequestHandlerV2._setup_active_task` calls
  `request_context_builder.build(...)` before `registry.get_or_create(...)`,
  so raising `InvalidParamsError` here means nothing is ever persisted and
  the executor never runs.

**Ordering caveat for `task_id` (AD-7).** For a `SendMessage` whose
`message.task_id` names an *existing* task, `_setup_active_task` looks the
task up in the store (`self._versioned_store.get(original_task_id, ...)`)
and raises the SDK's own `TaskNotFoundError` **before it ever calls this
builder** -- so for that common case (a caller echoing back a `taskId`),
the SDK's own store lookup is the first line of defense, not
`_validate_id_shape` below. This builder's `task_id`/`context_id` shape
check still matters in two cases: (a) a `contextId` is never looked up
against any store, so for it this check genuinely is the first thing that
runs; (b) this builder is also exercised directly (unit tests, and any
future caller that bypasses `_setup_active_task`'s pre-check), where there
is no implicit SDK lookup ahead of it. See
`tests/integration/a2a_server/test_a2a_runtime.py` for the pinned,
through-the-handler behaviour (malformed `taskId` -> `TaskNotFoundError`,
nothing created) and `tests/unit/services/a2a_server/test_context_builders.py`
for this builder's own validation in isolation. Router-level request
validation (step_017) is a separate, later line of defense and is out of
scope here.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlsplit

from a2a.extensions.common import HTTP_EXTENSION_HEADER, get_requested_extensions
from a2a.server.agent_execution import RequestContext, RequestContextBuilder
from a2a.server.agent_execution.simple_request_context_builder import (
    SimpleRequestContextBuilder,
)
from a2a.server.context import ServerCallContext
from a2a.server.routes.common import ServerCallContextBuilder
from a2a.types.a2a_pb2 import Message, Part, SendMessageRequest, Task
from a2a.utils.errors import InternalError, InvalidParamsError
from google.protobuf.struct_pb2 import Struct, Value

from services.a2a_server.identity import A2ACallerUser, owner_for
from utils.a2a_config import effective_max_file_bytes, get_a2a_config
from utils.logger import get_logger

if TYPE_CHECKING:
    from services.a2a_server.identity import A2ACallScope

logger = get_logger(__name__)

# AD-3: an allow-list copy only -- never x-api-key, authorization or cookie,
# because the SDK logs call_context (which embeds these headers) at DEBUG.
_ALLOWED_HEADER_NAMES = ("a2a-version", "a2a-extensions", "content-type", "user-agent")

# AD-7: client-supplied contextId/taskId must fit the SDK's String(36) columns
# and this charset. Mirrors services/a2a_server/context_binding_service.py's
# (step_013) own defense-in-depth check.
_ID_MAX_LENGTH = 36
_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")

# AD-7: a DataPart (or a metadata Struct) nested deeper than this is rejected.
_MAX_DATA_PART_DEPTH = 32

# Bounds that have no per-agent/per-app override (unlike the file-size cap,
# which goes through `effective_max_file_bytes`).
_MAX_URL_LENGTH = 2048
_MAX_FILENAME_LENGTH = 255
_MAX_MEDIA_TYPE_LENGTH = 255
_ALLOWED_URL_SCHEMES = ("http", "https")


class _MissingScopeError(RuntimeError):
    """Raised internally when `request.state.a2a_scope` is missing.

    Signals a router bug (AD-4 step 10 must set it before dispatch), not a
    client error. `A2AServerCallContextBuilder.build` catches this and
    re-raises a generic SDK `InternalError` (never surfaced with internal
    detail to the caller) -- this exception type exists only so the
    `build()` call site and its tests can tell the "scope missing" case
    apart from an attribute lookup going wrong for some other reason.
    """


class A2AServerCallContextBuilder(ServerCallContextBuilder):
    """Builds the SDK's `ServerCallContext` from the AD-4 router's `request.state.a2a_scope`."""

    def build(self, request) -> ServerCallContext:
        scope: Optional["A2ACallScope"] = getattr(request.state, "a2a_scope", None)
        if scope is None:
            logger.error(
                "a2a.context_builder.missing_scope path=%s; the A2A router must resolve and "
                "set request.state.a2a_scope before dispatching to JsonRpcDispatcher.handle_requests "
                "(AD-4)",
                getattr(getattr(request, "url", None), "path", None),
            )
            # Generic message only -- this is a server-side wiring bug, not a client
            # error, so no internal detail (path, scope state) is returned to the caller.
            raise InternalError(message="internal server error")
        owner = owner_for(scope.app_id, scope.agent_id, scope.api_key_hash)
        return ServerCallContext(
            user=A2ACallerUser(owner),
            state={"a2a": scope, "headers": _allow_listed_headers(request.headers)},
            requested_extensions=get_requested_extensions(
                request.headers.getlist(HTTP_EXTENSION_HEADER)
            ),
        )


def _allow_listed_headers(headers) -> dict:
    """Copies only the allow-listed header names, lowercased (AD-3)."""
    result = {}
    for name in _ALLOWED_HEADER_NAMES:
        value = headers.get(name)
        if value is not None:
            result[name] = value
    return result


def _validate_id_shape(value: str, *, field_name: str) -> None:
    if len(value) > _ID_MAX_LENGTH or not _ID_PATTERN.match(value):
        logger.warning("a2a.request_context.invalid_id field=%s length=%s", field_name, len(value))
        raise InvalidParamsError(message=f"{field_name} must be at most 36 characters of [A-Za-z0-9._:-]")


def _value_depth(value: Value, current: int = 1) -> int:
    """Recursively measures the nesting depth of a `google.protobuf.Value` (a DataPart)."""
    kind = value.WhichOneof("kind")
    if kind == "struct_value":
        fields = value.struct_value.fields
        if not fields:
            return current
        return max(_value_depth(v, current + 1) for v in fields.values())
    if kind == "list_value":
        items = value.list_value.values
        if not items:
            return current
        return max(_value_depth(v, current + 1) for v in items)
    return current


def _struct_depth(struct: Struct) -> int:
    """Nesting depth of a `google.protobuf.Struct` (a `Message`/`Part` `metadata` field),
    measured the same way as `_value_depth` so the two share one depth cap."""
    if not struct.fields:
        return 1
    return max(_value_depth(v, 2) for v in struct.fields.values())


def _effective_cap(scope: Optional["A2ACallScope"]) -> int:
    app_max_file_size_mb = scope.snapshot.app_max_file_size_mb if scope is not None else None
    return effective_max_file_bytes(app_max_file_size_mb)


def _validate_metadata(struct: Optional[Struct], *, scope: Optional["A2ACallScope"], label: str) -> None:
    """Bounds a `metadata` `Struct` (on `Message` or `Part`) with the same
    depth/size checks as a `DataPart` (item 2 of the step_012 fix round)."""
    if struct is None or not struct.fields:
        return
    depth = _struct_depth(struct)
    if depth > _MAX_DATA_PART_DEPTH:
        logger.warning("a2a.request_context.metadata_too_deep label=%s depth=%s", label, depth)
        raise InvalidParamsError(message=f"{label} metadata is nested too deeply")
    cap = _effective_cap(scope)
    size = struct.ByteSize()
    if size > cap:
        logger.warning("a2a.request_context.metadata_too_large label=%s size=%s cap=%s", label, size, cap)
        raise InvalidParamsError(message=f"{label} metadata exceeds the per-file size limit")


def _validate_url(url: str) -> None:
    if not url:
        raise InvalidParamsError(message="file url must not be empty")
    if len(url) > _MAX_URL_LENGTH:
        logger.warning("a2a.request_context.url_too_long length=%s", len(url))
        raise InvalidParamsError(message=f"file url must be at most {_MAX_URL_LENGTH} characters")
    scheme = urlsplit(url).scheme.lower()
    if scheme not in _ALLOWED_URL_SCHEMES:
        logger.warning("a2a.request_context.url_bad_scheme scheme=%s", scheme)
        raise InvalidParamsError(message="file url must use http or https")


def _validate_part_strings(part: Part) -> None:
    if part.filename and len(part.filename) > _MAX_FILENAME_LENGTH:
        raise InvalidParamsError(message=f"filename must be at most {_MAX_FILENAME_LENGTH} characters")
    if part.media_type and len(part.media_type) > _MAX_MEDIA_TYPE_LENGTH:
        raise InvalidParamsError(
            message=f"media_type must be at most {_MAX_MEDIA_TYPE_LENGTH} characters"
        )


def _validate_part(part: Part, *, scope: Optional["A2ACallScope"]) -> tuple[bool, int]:
    """Validates one `Part` (content, metadata, filename/media_type length).

    Returns `(has_content, byte_size)`: `has_content` is True unless the
    part is whitespace-only text (AC-29); `byte_size` feeds the aggregate
    per-message size cap (item 2).
    """
    _validate_part_strings(part)
    _validate_metadata(part.metadata if part.HasField("metadata") else None, scope=scope, label="part")

    which = part.WhichOneof("content")
    if which == "text":
        return bool(part.text.strip()), len(part.text.encode("utf-8"))
    if which == "raw":
        cap = _effective_cap(scope)
        if len(part.raw) > cap:
            logger.warning("a2a.request_context.inline_file_too_large size=%s cap=%s", len(part.raw), cap)
            raise InvalidParamsError(message="inline file content exceeds the per-file size limit")
        return True, len(part.raw)
    if which == "url":
        _validate_url(part.url)
        return True, 0
    if which == "data":
        depth = _value_depth(part.data)
        if depth > _MAX_DATA_PART_DEPTH:
            logger.warning("a2a.request_context.data_part_too_deep depth=%s", depth)
            raise InvalidParamsError(message="data part is nested too deeply")
        size = part.data.ByteSize()
        cap = _effective_cap(scope)
        if size > cap:
            logger.warning("a2a.request_context.data_part_too_large size=%s cap=%s", size, cap)
            raise InvalidParamsError(message="data part exceeds the per-file size limit")
        return True, size
    # Neither text, raw, url nor data is set: an empty Part carries no content.
    logger.warning("a2a.request_context.empty_part")
    raise InvalidParamsError(message="a message part must set text, file content or data")


def _validate_message(message: Optional[Message], *, scope: Optional["A2ACallScope"]) -> None:
    if message is None:
        return
    cfg = get_a2a_config()

    parts = list(message.parts)
    if not parts:
        raise InvalidParamsError(message="message must contain at least one part")
    if len(parts) > cfg.max_parts:
        logger.warning("a2a.request_context.too_many_parts count=%s cap=%s", len(parts), cfg.max_parts)
        raise InvalidParamsError(message=f"message must contain at most {cfg.max_parts} parts")

    has_content = False
    total_bytes = 0
    file_part_count = 0
    for part in parts:
        part_has_content, part_bytes = _validate_part(part, scope=scope)
        has_content = has_content or part_has_content
        total_bytes += part_bytes
        if part.WhichOneof("content") in ("raw", "url"):
            file_part_count += 1

    if file_part_count > cfg.max_file_parts:
        logger.warning(
            "a2a.request_context.too_many_file_parts count=%s cap=%s", file_part_count, cfg.max_file_parts
        )
        raise InvalidParamsError(message=f"message must contain at most {cfg.max_file_parts} file parts")
    if not has_content:
        raise InvalidParamsError(message="message text must not be empty or only whitespace")

    max_request_bytes = cfg.max_request_mb * 1024 * 1024
    if total_bytes > max_request_bytes:
        logger.warning(
            "a2a.request_context.message_too_large size=%s cap=%s", total_bytes, max_request_bytes
        )
        raise InvalidParamsError(message="message exceeds the maximum total request size")

    _validate_metadata(
        message.metadata if message.HasField("metadata") else None, scope=scope, label="message"
    )


class A2ARequestContextBuilder(RequestContextBuilder):
    """Validates, then delegates to `SimpleRequestContextBuilder` (AD-7).

    Every rejection here raises `a2a.utils.errors.InvalidParamsError` before
    `SimpleRequestContextBuilder.build` runs, so no `Task` row is ever
    created for a rejected request (`should_populate_referred_tasks=False`,
    `task_store=None`: this builder never reads the store either). See the
    module docstring for the `task_id` ordering caveat relative to the SDK's
    own store lookup.
    """

    def __init__(self) -> None:
        self._delegate = SimpleRequestContextBuilder(
            should_populate_referred_tasks=False, task_store=None
        )

    async def build(
        self,
        context: ServerCallContext,
        params: Optional[SendMessageRequest] = None,
        task_id: Optional[str] = None,
        context_id: Optional[str] = None,
        task: Optional[Task] = None,
    ) -> RequestContext:
        scope: Optional["A2ACallScope"] = context.state.get("a2a") if context.state else None

        if task_id is not None:
            _validate_id_shape(task_id, field_name="taskId")
        if context_id is not None:
            _validate_id_shape(context_id, field_name="contextId")
        if params is not None:
            _validate_message(params.message, scope=scope)

        request_context = await self._delegate.build(
            context=context, params=params, task_id=task_id, context_id=context_id, task=task
        )

        if scope is not None and scope.request_log is not None:
            scope.request_log.task_id = request_context.task_id
            scope.request_log.context_id = request_context.context_id

        return request_context


__all__ = ["A2AServerCallContextBuilder", "A2ARequestContextBuilder"]
