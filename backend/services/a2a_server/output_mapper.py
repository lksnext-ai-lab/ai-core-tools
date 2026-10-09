"""A2A output mapper (step_015): typed stream events -> A2A artifacts/status.

``ResponseArtifactMapper`` is the pure translation layer between
``AgentStreamingService.stream_agent_events``'s typed ``AgentStreamEvent``
(see ``tools.streaming_utils``, AD-5) and the small set of ``MapperAction``
values the executor bridge (step_016, ``backend/services/a2a_server/executor.py``)
applies through ``a2a.server.tasks.TaskUpdater``. It never touches the SDK's
event queue, and it never renders or parses SSE text -- the sibling test
module asserts this with a source grep (no ``"data: "`` literal, no
``format_sse_event`` import).

Error mapping (RB-7, carried into this step by the orchestrator): errors are
sanitized on ``extra["error_kind"]`` -- the stable, closed vocabulary
``AgentStreamingService`` documents (``connection``, ``incomplete_turn``,
``http``, ``serialization``, ``agent_failure``) -- never on
``extra["error_code"]`` (a raw exception class name / internal code, not a
vocabulary a switch should be written against). ``extra["detail"]`` is only
ever surfaced to the A2A caller when ``error_kind == "http"`` **and** the
status code is in the 4xx range (a caller-facing detail written by our own
``_prepare_turn``); 5xx and every other kind fall back to a fixed generic
message, never the exception text or a stack trace.

Final-text authority (AD-5, also carried into this step): the ``done``
event's ``data["response"]`` is authoritative over this mapper's own running
concatenation of streamed ``token`` events. ``_finalize_turn`` can append
content after the last token was streamed (file markers), and the
missing-tool-output retry path can replace a turn's visible text outright
before any token of the *winning* attempt is streamed. So the final
``TextPart`` this mapper emits is always computed as the suffix of the
authoritative text not yet covered by what was actually sent via
``AppendText`` -- never a fresh re-render of the authoritative text on top of
what streaming already delivered (AC-15: the ``response`` artifact's
concatenated text chunks must equal the final text exactly, with no
duplication).
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
import os
from dataclasses import dataclass
from typing import Any, Optional, Protocol, Union

from google.protobuf.json_format import Parse
from google.protobuf.struct_pb2 import Value

from a2a.types import Part

from services.file_management_service import FileManagementService
from tools.streaming_utils import (
    AgentStreamEvent,
    SSE_CODE_OUTPUT,
    SSE_DONE,
    SSE_ERROR,
    SSE_METADATA,
    SSE_THINKING,
    SSE_TOKEN,
    SSE_TOOL_END,
    SSE_TOOL_START,
)
from utils.async_files import read_bytes
from utils.logger import get_logger
from utils.path_safety import UnsafePathError, resolve_within
from utils.security import build_expiring_static_url

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Mapper actions -- the bridge (step_016) applies each of these through
# `a2a.server.tasks.TaskUpdater`. Plain strings only (never a `Message`/
# `Artifact`): building those SDK objects is the bridge's job, since it owns
# the `TaskUpdater` instance (task_id/context_id) this mapper has no access to.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AppendText:
    """Append ``text`` to the streaming ``"response"`` artifact (``append=True``)."""

    text: str


@dataclass(frozen=True, slots=True)
class StatusMessage:
    """A transient, non-persisted status update (only emitted when enabled)."""

    text: str


@dataclass(frozen=True, slots=True)
class Final:
    """The turn's final parts.

    ``parts`` is, in order: the remaining (not yet streamed) response text as
    a text ``Part`` -- always present, even when empty, so the bridge has a
    reliable last chunk to mark ``append=True, last_chunk=True`` on the
    ``"response"`` artifact -- then an optional structured ``Part`` (JSON
    ``DataPart``), then zero or more file ``Part``s. The bridge groups these
    by which of ``Part``'s oneof fields is populated (``text``/``data``/
    ``raw``/``url``) into the ``"response"``, ``"structured"`` and ``"files"``
    artifacts respectively -- this mapper does not know about artifact ids.
    """

    parts: list


@dataclass(frozen=True, slots=True)
class Fail:
    """Fail the task with an already-sanitized, user-facing message."""

    message: str


MapperAction = Union[AppendText, StatusMessage, Final, Fail]


# ---------------------------------------------------------------------------
# Error sanitization (RB-7): keyed on `extra["error_kind"]`, never
# `extra["error_code"]`. Vocabulary mirrors `AgentStreamingService`'s
# documented set exactly; anything outside it (including a missing/unknown
# `error_kind`) falls back to the generic message rather than raising.
# ---------------------------------------------------------------------------

_GENERIC_ERROR_MESSAGE = "Agent execution failed."
_ERROR_KIND_MESSAGES: dict[str, str] = {
    "connection": "Temporary connection error, please retry.",
    "incomplete_turn": _GENERIC_ERROR_MESSAGE,
    "serialization": _GENERIC_ERROR_MESSAGE,
    "agent_failure": _GENERIC_ERROR_MESSAGE,
    "approval": (
        "This agent needs human approval before running one of its tools, which A2A "
        "cannot provide. The tool was not executed."
    ),
    "pii_blocked": "The message was blocked because it contains personal data.",
    # "http" is handled separately below -- its message depends on the
    # status code, not a fixed string.
}

_MAX_HTTP_DETAIL_CHARS = 2000


def sanitize_error(extra: Optional[dict]) -> str:
    """Return the user-facing message for an ``error`` ``AgentStreamEvent``.

    Never returns the raw exception text or a stack trace. ``extra["detail"]``
    is surfaced only for ``error_kind == "http"`` with a 4xx status code --
    that is the one case where the text was already written for a caller
    (``_prepare_turn``'s ``HTTPException.detail``, e.g. a quota or
    conversation-ownership message). Every other kind, including 5xx HTTP
    and an unrecognized/missing ``error_kind``, gets the fixed generic
    message.
    """
    extra = extra or {}
    kind = extra.get("error_kind")

    if kind == "http":
        status_code = extra.get("status_code")
        detail = extra.get("detail")
        if isinstance(status_code, int) and 400 <= status_code < 500 and detail:
            return str(detail)[:_MAX_HTTP_DETAIL_CHARS]
        return _GENERIC_ERROR_MESSAGE

    return _ERROR_KIND_MESSAGES.get(kind, _GENERIC_ERROR_MESSAGE)


# ---------------------------------------------------------------------------
# File resolution -- injected so the mapper's own tests never touch disk.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FileResolution:
    """What the mapper needs to turn one ``files_data`` entry into a ``Part``."""

    abs_path: str
    rel_path: str
    size: int
    media_type: str


class FileResolver(Protocol):
    """Resolves an output file's id to its on-disk location and metadata."""

    async def resolve(self, file_id: str) -> Optional[FileResolution]:
        ...


class DefaultFileResolver:
    """Resolves A2A turn output files via ``FileManagementService.get_session_file``.

    Scoped to one ``(agent_id, user_context, conversation_id)`` triple --
    build a fresh instance per turn, mirroring the fresh
    ``FileManagementService()`` the executor bridge builds for input
    processing (FR-16/NFR-4: no session or service instance is shared across
    turns).

    Uses only ``FileManagementService``'s public surface: ``get_session_file``
    does the session-scoped, path-contained lookup (it is what lets this
    resolver see a file a *different* ``FileManagementService`` instance
    registered earlier in the same turn -- the one
    ``AgentExecutionService._finalize_turn`` builds and discards internally
    for ``sync_output_files``), and ``tmp_base_folder`` is a public,
    read-only property. No private attribute of ``FileManagementService`` is
    touched here, and every filesystem call is off the event loop
    (``asyncio.to_thread``).
    """

    def __init__(
        self,
        agent_id: int,
        user_context: Optional[dict],
        conversation_id: Any,
        fms: Optional[FileManagementService] = None,
    ) -> None:
        self._agent_id = agent_id
        self._user_context = user_context
        self._conversation_id = (
            str(conversation_id) if conversation_id is not None else None
        )
        self._fms = fms if fms is not None else FileManagementService()

    async def resolve(self, file_id: str) -> Optional[FileResolution]:
        ref = await self._fms.get_session_file(
            self._agent_id, self._user_context, self._conversation_id, file_id,
        )
        if ref is None or not ref.file_path:
            logger.warning(
                "A2A output mapper: output file_id not found for its session "
                "(agent_id=%s)",
                self._agent_id,
            )
            return None

        try:
            abs_path = resolve_within(self._fms.tmp_base_folder, ref.file_path)
        except UnsafePathError:
            # get_session_file() already applies this same check, but a
            # second, independent check here costs nothing and keeps this
            # resolver safe even if that contract ever changes.
            logger.warning(
                "A2A output mapper: output file_path escaped TMP_BASE_FOLDER "
                "(agent_id=%s); refusing to resolve it",
                self._agent_id,
            )
            return None

        exists = await asyncio.to_thread(os.path.isfile, abs_path)
        if not exists:
            logger.warning(
                "A2A output mapper: resolved output file is missing on disk "
                "(agent_id=%s)",
                self._agent_id,
            )
            return None

        size = ref.file_size_bytes
        if size is None:
            size = await asyncio.to_thread(os.path.getsize, abs_path)

        media_type = (
            ref.mime_type
            or mimetypes.guess_type(ref.filename or "")[0]
            or "application/octet-stream"
        )

        return FileResolution(
            abs_path=abs_path,
            rel_path=ref.file_path,
            size=size,
            media_type=media_type,
        )


# ---------------------------------------------------------------------------
# Status-update text (only emitted when `status_updates` is enabled). Two
# fixed strings only -- never `data["message"]`, never
# `tools.streaming_utils.get_thinking_message`, never a tool/agent name or
# any other caller/LLM-controlled text. See AD-15 `A2A_STATUS_UPDATES` and
# NFR-5: a status update is a liveness signal, not a content channel, and a
# tool name or message can itself be attacker-influenced (prompt injection
# surfaces further downstream than this module, but this is one more place
# that must not echo it).
# ---------------------------------------------------------------------------

_STATUS_TEXT_USING_A_TOOL = "Using a tool..."
_STATUS_TEXT_WORKING = "Working..."


def _status_text(event: AgentStreamEvent) -> str:
    if event.type == SSE_TOOL_START:
        return _STATUS_TEXT_USING_A_TOOL
    # thinking / tool_end / code_output all collapse to the same generic text.
    return _STATUS_TEXT_WORKING


# ---------------------------------------------------------------------------
# The mapper
# ---------------------------------------------------------------------------


class ResponseArtifactMapper:
    """Maps one turn's ``AgentStreamEvent`` stream to ``MapperAction`` values.

    One stable artifact identity is implied for the streamed text: id
    ``"response"``, name ``"response"`` (the bridge is responsible for using
    exactly this id/name on every ``AppendText`` it applies, and for the
    text ``Part`` inside ``Final.parts``, so all of a turn's text lands in
    one artifact).

    Token coalescing: ``AppendText`` is produced immediately for the first
    token (first-chunk latency, NFR-8), and from then on at most once per
    ``coalesce_ms`` -- call :meth:`flush_due` on a timer so a final silent
    buffer is not held past its window; the bridge's own keepalive ticker is
    the natural place for that (AD-6).

    Never produces an ``input_required`` action -- there is no such
    ``MapperAction``.

    Inline file budget: in addition to the per-file ``inline_file_max_bytes``
    cap, a running budget for the whole turn starts at
    ``inline_file_max_bytes`` and is debited by every file actually inlined.
    Once it is exhausted, later files in the same ``done`` -- even ones
    individually under the per-file cap -- fall back to the signed-URL form.
    This bounds the total bytes a single turn can inline regardless of how
    many small files it produces.
    """

    def __init__(
        self,
        coalesce_ms: int,
        status_updates: bool = False,
        file_resolver: Optional[FileResolver] = None,
        base_url: Optional[str] = None,
        identity: str = "",
        file_url_ttl_seconds: int = 3600,
        inline_file_max_bytes: int = 5242880,
    ) -> None:
        if base_url and not identity:
            raise ValueError(
                "identity is required when base_url is set: a signed file URL "
                "cannot be built without the identity to bind into it."
            )

        self._coalesce_ms = max(0, coalesce_ms)
        self._status_updates = status_updates
        self._file_resolver = file_resolver
        self._base_url = base_url
        self._identity = identity
        self._file_url_ttl_seconds = file_url_ttl_seconds
        self._inline_file_max_bytes = inline_file_max_bytes
        self._inline_budget_remaining = inline_file_max_bytes

        self._pending: str = ""
        self._window_start: Optional[float] = None
        self._flushed_once: bool = False
        self._sent_text: str = ""

        #: Captured from the `metadata` event, for callers that want it;
        #: this mapper does not use it itself (the file resolver already has
        #: its own conversation_id injected at construction time).
        self.conversation_id: Optional[int] = None

    # ------------------------------------------------------------------
    # Token coalescing
    # ------------------------------------------------------------------

    def handle_token(self, text: str, now: float) -> Optional[AppendText]:
        """Buffer ``text``; return an ``AppendText`` if this flushes the buffer."""
        if not text:
            return None
        self._pending += text
        if not self._flushed_once:
            # The very first chunk always flushes immediately (NFR-8).
            return self._flush()
        if self._window_start is None:
            self._window_start = now
        if (now - self._window_start) * 1000 >= self._coalesce_ms:
            return self._flush()
        return None

    def flush_due(self, now: float) -> Optional[AppendText]:
        """Flush the buffer if its coalescing window has elapsed.

        Call this on a timer (the bridge's keepalive ticker, AD-6) so a
        buffer that stops receiving tokens is not held past
        ``coalesce_ms`` while the stream stays otherwise silent.
        """
        if not self._pending or self._window_start is None:
            return None
        if (now - self._window_start) * 1000 >= self._coalesce_ms:
            return self._flush()
        return None

    def drain(self) -> Optional[AppendText]:
        """Flush whatever remains in the buffer right now, unconditionally."""
        if not self._pending:
            return None
        return self._flush()

    def _flush(self) -> Optional[AppendText]:
        text = self._pending
        self._pending = ""
        self._window_start = None
        self._flushed_once = True
        if not text:
            return None
        self._sent_text += text
        return AppendText(text)

    # ------------------------------------------------------------------
    # Main dispatch
    # ------------------------------------------------------------------

    async def apply(self, event: AgentStreamEvent, now: float) -> list[MapperAction]:
        """Map one ``AgentStreamEvent`` to zero or more ``MapperAction`` values."""
        if event.type == SSE_TOKEN:
            action = self.handle_token(event.data.get("content", "") or "", now)
            return [action] if action is not None else []

        if event.type == SSE_METADATA:
            conv_id = event.data.get("conversation_id")
            if conv_id is not None:
                self.conversation_id = conv_id
            return []

        if event.type in (SSE_THINKING, SSE_TOOL_START, SSE_TOOL_END, SSE_CODE_OUTPUT):
            if not self._status_updates:
                return []
            return [StatusMessage(_status_text(event))]

        if event.type == SSE_ERROR:
            return [Fail(sanitize_error(event.extra))]

        if event.type == SSE_DONE:
            return await self._handle_done(event.data or {}, event.extra or {})

        # Unknown event type: ignore rather than raise, matching the
        # "never input_required, never raise on an unrecognized event"
        # posture the bridge relies on to stay in exactly one terminal
        # state per turn.
        logger.warning("A2A output mapper: ignoring unrecognized event type %r", event.type)
        return []

    async def _handle_done(self, data: dict, extra: dict) -> list[MapperAction]:
        actions: list[MapperAction] = []

        drained = self.drain()
        if drained is not None:
            actions.append(drained)

        parts = [Part(text=self._resolve_remaining_text(data, extra))]

        structured = extra.get("structured")
        parsed_response = extra.get("parsed_response")
        if structured and isinstance(parsed_response, (dict, list)):
            parts.append(_build_data_part(parsed_response))

        for file_meta in extra.get("files_data") or []:
            part = await self._resolve_file_part(file_meta)
            if part is not None:
                parts.append(part)

        actions.append(Final(parts))
        return actions

    def _resolve_remaining_text(self, data: dict, extra: dict) -> str:
        """Return the suffix of the authoritative final text not yet streamed.

        ``data["response"]`` is authoritative over this mapper's own running
        concatenation of streamed tokens (AD-5). When the authoritative text
        is a non-empty string that starts with what was already sent, the
        remainder is the exact suffix still owed to the ``"response"``
        artifact -- this is what keeps AC-15's "concatenation equals the
        final text exactly" true without resending anything.

        If the authoritative text is not a string (structured output) or
        is empty, the already-sent text is itself the best-known full text.
        If *that* is also empty (no tokens were ever streamed, e.g. a
        structured-only turn), the parsed response is rendered as JSON so
        the ``"response"`` artifact is never completely empty when
        ``extra["structured"]`` carries real content.
        """
        response = data.get("response")
        if isinstance(response, str) and response:
            full_text = response
        elif self._sent_text:
            full_text = self._sent_text
        else:
            parsed_response = extra.get("parsed_response")
            if parsed_response is not None:
                try:
                    full_text = json.dumps(parsed_response, ensure_ascii=False)
                except (TypeError, ValueError):
                    full_text = str(parsed_response)
            else:
                full_text = ""

        if self._sent_text and not full_text.startswith(self._sent_text):
            # The authoritative text diverged from what streaming already
            # sent (e.g. a retry replaced the turn's visible content without
            # emitting a fresh `token` of its own). There is no way to un-send
            # the earlier chunks, so the best remaining option is to make the
            # *authoritative* text win outright rather than silently drop the
            # divergence.
            logger.warning(
                "A2A output mapper: final text is not a continuation of the "
                "streamed text; sending the full authoritative text instead "
                "of a diff (AD-5 authoritative-response rule)."
            )
            return full_text

        return full_text[len(self._sent_text):]

    def _fits_inline_budget(self, size: int) -> bool:
        return size <= self._inline_file_max_bytes and size <= self._inline_budget_remaining

    async def _resolve_file_part(self, file_meta: dict) -> Optional[Part]:
        file_id = file_meta.get("file_id")
        filename = file_meta.get("filename")
        if not file_id or not self._file_resolver:
            return None

        resolution = await self._file_resolver.resolve(file_id)
        if resolution is None:
            return None

        if self._fits_inline_budget(resolution.size):
            # The resolver's reported size can be stale by the time we get
            # here (another request could have rewritten the file). Re-check
            # on disk right before reading, and once more against the
            # bytes actually read, so a file that grew past either cap in
            # the meantime is never inlined in full.
            stat_result = await asyncio.to_thread(os.stat, resolution.abs_path)
            if self._fits_inline_budget(stat_result.st_size):
                content = await read_bytes(resolution.abs_path)
                if self._fits_inline_budget(len(content)):
                    self._inline_budget_remaining -= len(content)
                    return Part(
                        raw=content, filename=filename or "", media_type=resolution.media_type
                    )

        if not self._base_url:
            logger.warning(
                "A2A output mapper: no base_url configured; cannot build a "
                "signed URL for a file over the inline size/budget cap -- dropping it."
            )
            return None

        url = build_expiring_static_url(
            self._base_url,
            resolution.rel_path,
            identity=self._identity,
            ttl_seconds=self._file_url_ttl_seconds,
            filename=filename,
        )
        return Part(url=url, filename=filename or "", media_type=resolution.media_type)


def _build_data_part(value: Any) -> Part:
    """Build a ``DataPart`` (``Part.data``) from a JSON-compatible value.

    AC-22: ``media_type`` is always ``"application/json"`` on a ``DataPart``.
    """
    pb_value = Value()
    Parse(json.dumps(value), pb_value)
    return Part(data=pb_value, media_type="application/json")
