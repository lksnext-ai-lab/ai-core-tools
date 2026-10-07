"""Input processing: A2A ``Message`` parts -> chat text + file references (FR-18, NFR-5).

``build_turn_inputs`` is the single place that turns an inbound A2A
``a2a.types.Message`` into the ``(text, file_refs)`` pair the executor bridge
(step_016) hands to ``AgentExecutionService``/``AgentStreamingService``,
exactly as the public API's ``/call`` and ``/call/stream`` routers do for an
HTTP multipart request (``backend/routers/public/v1/chat.py``).

Per-part rules (FR-18):
- **text** parts are joined with ``\\n\\n``.
- **data** parts are rendered as a fenced ```json`` block and appended to the
  text in the same relative order (AC-25).
- **file parts with bytes** go straight through ``FileManagementService.upload_file``,
  with ``strict=True`` (FR-18: never a placeholder — see that method's docstring).
- **file parts with a URI** are fetched through the shared SSRF guard
  (``utils.ssrf_guard.fetch_bytes``) before being uploaded the same way.
  http/https only; every redirect is re-validated; TLS verification is always
  on; there is no retry and no ``verify=False`` (AC-26, AC-27, NFR-5).

Any fetch/decode/upload failure raises :class:`A2AInputError`, naming the
part by its sanitized filename. Its message is safe to show the caller and
never includes file content, a URL, or raw exception text. **Never** is
placeholder content substituted for a part that failed; on any failure,
everything uploaded earlier in the same turn (ephemeral *and* persistent) is
cleaned up best-effort before the error propagates — including when the
turn is cancelled, not just when a part raises.

Caps (NFR-5, and the step_014 review's hardening round): a message is capped
at ``A2A_MAX_PARTS`` parts and ``A2A_MAX_FILE_PARTS`` file parts, checked
before any part is processed; every file (bytes or fetched) is capped at the
per-file limit *and* the remaining room under the total per-request cap,
whichever is smaller; every URI fetch in one turn shares a single wall-clock
budget (``A2A_URI_FETCH_TIMEOUT_SECONDS`` total, not per file), so N
attacker-controlled file parts can't multiply the deadline.

Logging is limited to part index, kind, media type, size and (for fetch
failures) the exception class name; for URI parts only the resolved host is
logged, never the URL (it may carry tokens), per the shared conventions and
NFR-5.
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import time
import unicodedata
import urllib.parse
from dataclasses import dataclass
from io import BytesIO
from typing import Any, List, Optional, Protocol, Sequence

from fastapi import HTTPException, UploadFile
from google.protobuf import json_format
from starlette.datastructures import Headers

import a2a.types as a2a_types

from services.file_management_service import (
    STORAGE_STRATEGY_PERSISTENT,
    FileManagementService,
    FileReference,
)
from utils.a2a_config import effective_max_file_bytes, get_a2a_config
from utils.logger import get_logger
from utils.ssrf_guard import (
    FetchError,
    FetchInvalidURLError,
    FetchStatusError,
    FetchTimeoutError,
    FetchTooLargeError,
    FetchTransportError,
    FetchUnresolvableError,
    SsrfBlockedError,
    TooManyRedirectsError,
    fetch_bytes,
)

logger = get_logger(__name__)

_ALLOWED_URI_SCHEMES = ("http", "https")

# Filename hardening (review round 1, item 3): cap at ~200 UTF-8 bytes
# (comfortably under every common filesystem's 255-byte limit, while leaving
# room for sidecar suffixes), and strip characters that could make a crafted
# filename confusing or unsafe to display back to the caller in an error
# message: C0/C1 controls, other "format" characters, and the explicit
# bidirectional-override code points (which Unicode's Cf category already
# includes, kept here as an explicit allow-list of what's always stripped).
_MAX_FILENAME_BYTES = 200
# Code points only, never literal characters: embedding the actual
# bidi-override characters in source text is itself a "Trojan Source" smell
# (and trips SAST bidi-character checks) — the exact thing this set exists
# to strip from untrusted filenames.
_BIDI_OVERRIDE_CODE_POINTS = (0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069)
_BIDI_OVERRIDES = frozenset(chr(code_point) for code_point in _BIDI_OVERRIDE_CODE_POINTS)

# Extensions _get_file_type already maps to a real (non-"unknown") type.
# Used only to decide whether a media-type-derived extension should be
# appended — never to second-guess FileManagementService's own typing.
_RECOGNIZED_EXTENSIONS = frozenset(
    (
        ".pdf",
        ".txt", ".md", ".json", ".csv",
        ".jpg", ".jpeg", ".png", ".gif", ".bmp",
        ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    )
)


class _AgentSnapshotLike(Protocol):
    """Structural shape this module needs from an agent snapshot.

    Deliberately duck-typed rather than importing a concrete class: the
    snapshot DTO (``services.a2a_server.snapshot.A2AAgentSnapshot``, step_011)
    is being built in a parallel step. Any object exposing these three
    attributes — including the real snapshot once it lands — satisfies this
    protocol; no import of step_011's module is required here.
    """

    agent_id: int
    app_max_file_size_mb: Optional[int]
    has_memory: bool


class A2AInputError(Exception):
    """Raised when a single ``Message`` part cannot be turned into chat input.

    Args:
        part_index: 1-based index of the offending part, as shown to the
            caller. ``0`` denotes a whole-message problem (e.g. too many
            parts) rather than one specific part.
        reason: A short, client-safe reason. Never file content, a URL, or raw
            exception text.
        filename: The part's *sanitized* filename, if known, included in the
            message for clarity. Callers must pass the already-sanitized
            name (see ``_safe_filename``), never the raw, caller-supplied one.

    The message is safe to surface directly in a failed Task's status, e.g.
    ``"part 2 (file 'x.pdf'): file exceeds the maximum allowed size"``.
    """

    def __init__(self, part_index: int, reason: str, *, filename: Optional[str] = None) -> None:
        self.part_index = part_index
        self.reason = reason
        self.filename = filename
        if filename:
            message = f"part {part_index} (file '{filename}'): {reason}"
        else:
            message = f"part {part_index}: {reason}"
        super().__init__(message)


@dataclass(frozen=True)
class TurnInputs:
    """Result of :func:`build_turn_inputs`: chat text plus ordered file references."""

    text: str
    file_refs: List[FileReference]


def _normalize_numbers(value: Any) -> Any:
    """Recursively collapse whole-number floats to ``int``.

    ``google.protobuf.Struct``'s ``NumberValue`` is always a double, so
    ``json_format.MessageToDict``/``MessageToJson`` renders ``{"a": 1}`` as
    ``{"a": 1.0}``. AC-25 requires the agent to see ``{"a": 1}``, so any float
    with no fractional part is rendered as the equivalent int; genuine
    fractional values are left untouched.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: _normalize_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_numbers(item) for item in value]
    return value


def _render_data_block(data_value: Any) -> str:
    """Render a ``Part.data`` (a ``google.protobuf.Value``) as a fenced JSON block (AC-25)."""
    rendered = json_format.MessageToDict(data_value, preserving_proto_field_name=True)
    normalized = _normalize_numbers(rendered)
    return "```json\n" + json.dumps(normalized, ensure_ascii=False, indent=2) + "\n```"


def _strip_unsafe_chars(name: str) -> str:
    """Drop Unicode control/format characters and explicit bidi overrides.

    A crafted filename (NUL bytes, RTL overrides, other Cc/Cf characters)
    must never reach a log line, an error message, or the filesystem looking
    different from how it reads.
    """
    return "".join(
        ch for ch in name if ch not in _BIDI_OVERRIDES and unicodedata.category(ch) not in ("Cc", "Cf")
    )


def _cap_filename_bytes(name: str, *, max_bytes: int = _MAX_FILENAME_BYTES) -> str:
    """Cap *name* to ``max_bytes`` UTF-8 bytes, keeping the extension intact."""
    if len(name.encode("utf-8")) <= max_bytes:
        return name
    stem, ext = os.path.splitext(name)
    budget = max(max_bytes - len(ext.encode("utf-8")), 1)
    # errors="ignore" avoids ending mid-codepoint after a byte-boundary cut.
    truncated_stem = stem.encode("utf-8")[:budget].decode("utf-8", errors="ignore")
    return (truncated_stem or "file") + ext


def _clean_media_type(media_type: Optional[str]) -> Optional[str]:
    """Strip any ``;`` parameters (e.g. ``; charset=utf-8``) from a media type.

    ``mimetypes.guess_extension`` only recognizes a bare ``type/subtype``; fed
    ``"text/plain; charset=utf-8"`` verbatim it returns ``None``, silently
    defeating the media-type-derived extension fallback below.
    """
    if not media_type:
        return None
    cleaned = media_type.split(";", 1)[0].strip()
    return cleaned or None


def _ensure_recognized_extension(name: str, media_type: Optional[str]) -> str:
    """Append a media-type-derived extension when *name*'s own extension is unrecognized.

    Lets a part named e.g. ``"report"`` with ``media_type="application/pdf"``
    reach ``FileManagementService`` as ``"report.pdf"`` so it is classified
    as ``pdf`` (and actually extracted) instead of ``unknown``.
    """
    _, ext = os.path.splitext(name)
    if ext.lower() in _RECOGNIZED_EXTENSIONS:
        return name
    cleaned_media_type = _clean_media_type(media_type)
    guessed = mimetypes.guess_extension(cleaned_media_type) if cleaned_media_type else None
    return f"{name}{guessed}" if guessed else name


def _safe_filename(raw_filename: Optional[str], part_index: int, media_type: Optional[str]) -> str:
    """Sanitize a part-supplied filename, falling back to a synthetic name.

    ``os.path.basename`` strips any directory components, leading dots are
    dropped (no hidden files, no ``..`` traversal fragments), control/format
    characters and bidi overrides are stripped, a media-type-derived
    extension is appended when the name's own extension isn't one
    ``FileManagementService`` recognizes, and the result is capped to
    ``_MAX_FILENAME_BYTES``. An empty or missing filename falls back to
    ``part-{index}.{ext}`` using an extension guessed from the media type, or
    no extension at all if that fails.
    """
    if raw_filename:
        candidate = _strip_unsafe_chars(os.path.basename(raw_filename)).lstrip(".")
        if candidate:
            candidate = _ensure_recognized_extension(candidate, media_type)
            return _cap_filename_bytes(candidate)

    cleaned_media_type = _clean_media_type(media_type)
    ext = mimetypes.guess_extension(cleaned_media_type) if cleaned_media_type else None
    if ext:
        return f"part-{part_index}{ext}"
    return f"part-{part_index}"


def _fetch_error_reason(exc: FetchError) -> str:
    """Map a :class:`FetchError` subclass to a short, client-safe reason.

    Never the raw exception text: some subclasses (e.g. ``FetchTimeoutError``)
    embed the fetched URL in their message, which NFR-5 says must not reach
    the caller or a log line.
    """
    if isinstance(exc, FetchUnresolvableError):
        return "file URI host could not be resolved"
    if isinstance(exc, SsrfBlockedError):
        return "file URI resolves to a disallowed address"
    if isinstance(exc, FetchTooLargeError):
        return "file exceeds the maximum allowed size"
    if isinstance(exc, FetchTimeoutError):
        return "file fetch timed out"
    if isinstance(exc, TooManyRedirectsError):
        return "file fetch followed too many redirects"
    if isinstance(exc, FetchInvalidURLError):
        return "file URI is invalid"
    if isinstance(exc, FetchStatusError):
        return "file fetch failed"
    if isinstance(exc, FetchTransportError):
        return "file fetch failed due to a network or TLS error"
    return "file fetch failed"  # the FetchError base class itself (e.g. a bad Content-Encoding)


async def _upload_part(
    fms: FileManagementService,
    upload_file: UploadFile,
    *,
    part_index: int,
    filename: str,
    agent_id: int,
    user_context: dict,
    conversation_id: Optional[int],
    has_memory: bool,
) -> FileReference:
    """Upload one decoded/fetched part through the existing chat file pipeline.

    Mirrors ``FileManagementService.resolve_chat_files``'s per-file upload
    step, except errors are never swallowed here: ``resolve_chat_files`` only
    logs an upload failure and silently drops the file, which would silently
    drop an A2A part instead of failing the task (FR-18). ``strict=True`` is
    passed so an unsupported type or a genuine extraction failure raises
    instead of falling back to placeholder content; any exception becomes an
    :class:`A2AInputError` naming the part.
    """
    try:
        file_ref = await fms.upload_file(
            file=upload_file,
            agent_id=agent_id,
            user_context=user_context,
            conversation_id=conversation_id,
            has_memory=has_memory,
            strict=True,
        )
    except HTTPException as exc:
        # Only ever forward a *known*, caller-safe 4xx reason (e.g. "Unsupported
        # file type", "File processing failed"). A 5xx means something internal
        # went wrong in a way upload_file didn't anticipate; never forward that
        # detail string verbatim, it may embed raw exception text.
        reason = str(exc.detail) if 400 <= exc.status_code < 500 else "file upload failed"
        raise A2AInputError(part_index, reason, filename=filename) from exc
    except Exception as exc:
        raise A2AInputError(part_index, "file upload failed", filename=filename) from exc

    # Mirrors resolve_chat_files: tells agent execution to send the full
    # content this turn, since the file was never indexed by an attach step.
    file_ref.uploaded_this_turn = True
    return file_ref


async def _cleanup_turn_refs(
    fms: FileManagementService,
    refs: Sequence[FileReference],
    *,
    agent_id: int,
    user_context: dict,
    conversation_id: Optional[int],
) -> None:
    """Best-effort cleanup of everything uploaded so far in a failed turn.

    Ephemeral refs are removed via ``cleanup_ephemeral_refs``. Persistent
    refs (memory agent + conversation_id) are *not* touched by that method,
    so a failed turn would otherwise leave them permanently attached; they
    are explicitly removed here as well (review round 1, item 5), best-effort
    — a cleanup failure is logged and never masks the original error.
    """
    refs = list(refs)
    await fms.cleanup_ephemeral_refs(refs)

    persistent_ids = [
        ref.file_id for ref in refs if getattr(ref, "storage_strategy", None) == STORAGE_STRATEGY_PERSISTENT
    ]
    if not persistent_ids:
        return
    try:
        await fms.remove_files(
            persistent_ids,
            agent_id=agent_id,
            user_context=user_context,
            conversation_id=str(conversation_id) if conversation_id else None,
        )
    except Exception:
        logger.warning(
            "a2a.input.cleanup_persistent_failed agent_id=%s count=%s", agent_id, len(persistent_ids)
        )


async def build_turn_inputs(
    message: a2a_types.Message,
    *,
    snapshot: _AgentSnapshotLike,
    user_context: dict,
    conversation_id: Optional[int],
    fms: FileManagementService,
) -> TurnInputs:
    """Turn an inbound A2A ``Message`` into chat text plus file references.

    Args:
        message: The A2A ``Message`` carrying this turn's ``parts``.
        snapshot: Agent snapshot-like object; only ``agent_id``,
            ``app_max_file_size_mb`` and ``has_memory`` are read.
        user_context: The caller's user context (``create_api_key_user_context``
            plus ``caller_type_override``), passed straight through to the
            file pipeline.
        conversation_id: The bound Mattin conversation id (AD-9), or ``None``.
        fms: The ``FileManagementService`` instance to upload through.

    Returns:
        ``TurnInputs(text, file_refs)``. ``file_refs`` includes both files
        uploaded from this message's parts and previously attached files for
        the conversation (merged without duplicates, the way public chat
        does).

    Raises:
        A2AInputError: the message has too many parts/file parts, a part's
            content is empty/unsupported, a FilePart URI is blocked, too
            large, times out, or fails TLS verification, a FilePart exceeds
            the per-file or total-request cap, or the upload pipeline rejects
            the file (e.g. unsupported type). Placeholder content is never
            substituted for a failed part.

    On any failure — including the calling task being cancelled mid-fetch or
    mid-upload — every file reference created so far in this turn is cleaned
    up (ephemeral and persistent) before the error/cancellation propagates.
    """
    cfg = get_a2a_config()
    per_file_cap_bytes = effective_max_file_bytes(snapshot.app_max_file_size_mb)
    total_cap_bytes = cfg.max_request_mb * 1024 * 1024

    if len(message.parts) > cfg.max_parts:
        raise A2AInputError(0, f"message has more than {cfg.max_parts} parts")

    file_part_count = sum(1 for part in message.parts if part.WhichOneof("content") in ("raw", "url"))
    if file_part_count > cfg.max_file_parts:
        raise A2AInputError(0, f"message has more than {cfg.max_file_parts} file parts")

    text_segments: List[str] = []
    new_refs: List[FileReference] = []
    total_file_bytes = 0
    # One wall-clock budget shared by every URI fetch in this turn (review
    # round 1, item 6): N file-uri parts can't multiply the deadline by N.
    remaining_fetch_budget_s = float(cfg.uri_fetch_timeout_seconds)
    turn_succeeded = False

    try:
        for part_index, part in enumerate(message.parts, start=1):
            kind = part.WhichOneof("content")

            if kind == "text":
                if part.text:
                    text_segments.append(part.text)
                logger.info("a2a.input.part index=%s kind=text size=%s", part_index, len(part.text))

            elif kind == "data":
                text_segments.append(_render_data_block(part.data))
                logger.info("a2a.input.part index=%s kind=data", part_index)

            elif kind == "raw":
                filename = _safe_filename(part.filename or None, part_index, part.media_type or None)
                remaining_total_bytes = total_cap_bytes - total_file_bytes
                if remaining_total_bytes <= 0:
                    raise A2AInputError(
                        part_index, "total attached file size exceeds the maximum allowed", filename=filename
                    )

                data = bytes(part.raw)
                size = len(data)
                effective_cap = min(per_file_cap_bytes, remaining_total_bytes)
                if size > effective_cap:
                    raise A2AInputError(part_index, "file exceeds the maximum allowed size", filename=filename)
                total_file_bytes += size

                logger.info(
                    "a2a.input.part index=%s kind=file_bytes media_type=%s size=%s",
                    part_index, part.media_type or None, size,
                )
                upload_file = UploadFile(
                    file=BytesIO(data),
                    filename=filename,
                    headers=Headers({"content-type": part.media_type or "application/octet-stream"}),
                )
                new_refs.append(
                    await _upload_part(
                        fms,
                        upload_file,
                        part_index=part_index,
                        filename=filename,
                        agent_id=snapshot.agent_id,
                        user_context=user_context,
                        conversation_id=conversation_id,
                        has_memory=snapshot.has_memory,
                    )
                )

            elif kind == "url":
                display_filename = _safe_filename(part.filename or None, part_index, part.media_type or None)
                url = part.url
                parsed = urllib.parse.urlsplit(url)
                scheme = parsed.scheme.lower()
                if scheme not in _ALLOWED_URI_SCHEMES:
                    raise A2AInputError(
                        part_index, "only http/https file URIs are supported", filename=display_filename
                    )

                remaining_total_bytes = total_cap_bytes - total_file_bytes
                if remaining_total_bytes <= 0:
                    raise A2AInputError(
                        part_index, "total attached file size exceeds the maximum allowed", filename=display_filename
                    )
                if remaining_fetch_budget_s <= 0:
                    raise A2AInputError(part_index, "file fetch time budget exhausted", filename=display_filename)

                logger.info(
                    "a2a.input.part index=%s kind=file_uri host=%s", part_index, parsed.hostname or "unknown"
                )
                fetch_timeout_s = min(float(cfg.uri_fetch_timeout_seconds), remaining_fetch_budget_s)
                fetch_started_at = time.monotonic()
                try:
                    fetched = await fetch_bytes(
                        url,
                        max_bytes=min(per_file_cap_bytes, remaining_total_bytes),
                        timeout_s=fetch_timeout_s,
                        max_redirects=3,
                    )
                except FetchError as exc:
                    logger.info(
                        "a2a.input.fetch_failed index=%s error=%s", part_index, type(exc).__name__
                    )
                    raise A2AInputError(
                        part_index, _fetch_error_reason(exc), filename=display_filename
                    ) from None
                except (asyncio.CancelledError, A2AInputError):
                    raise
                except Exception as exc:
                    # fetch_bytes's own contract is "every error is a FetchError", but
                    # this is the last line of defense: an unexpected bug or a future
                    # SDK/library change must still fail the part with a generic,
                    # client-safe reason instead of leaking a raw exception upward.
                    logger.info(
                        "a2a.input.fetch_failed_unexpected index=%s error=%s", part_index, type(exc).__name__
                    )
                    raise A2AInputError(part_index, "file fetch failed", filename=display_filename) from None
                finally:
                    remaining_fetch_budget_s -= time.monotonic() - fetch_started_at

                size = len(fetched.content)
                total_file_bytes += size
                filename = _safe_filename(
                    part.filename or fetched.filename, part_index, part.media_type or fetched.media_type
                )
                if total_file_bytes > total_cap_bytes:
                    raise A2AInputError(
                        part_index, "total attached file size exceeds the maximum allowed", filename=filename
                    )

                logger.info(
                    "a2a.input.part index=%s kind=file_uri_fetched media_type=%s size=%s",
                    part_index, part.media_type or fetched.media_type, size,
                )
                upload_file = UploadFile(
                    file=BytesIO(fetched.content),
                    filename=filename,
                    headers=Headers(
                        {"content-type": part.media_type or fetched.media_type or "application/octet-stream"}
                    ),
                )
                new_refs.append(
                    await _upload_part(
                        fms,
                        upload_file,
                        part_index=part_index,
                        filename=filename,
                        agent_id=snapshot.agent_id,
                        user_context=user_context,
                        conversation_id=conversation_id,
                        has_memory=snapshot.has_memory,
                    )
                )

            else:
                raise A2AInputError(part_index, "part has no supported content")

        existing_refs = await fms.resolve_chat_files(
            files=None,
            file_reference_ids=None,
            agent_id=snapshot.agent_id,
            user_context=user_context,
            conversation_id=conversation_id,
            has_memory=snapshot.has_memory,
        )
        turn_succeeded = True
    finally:
        # try/finally (rather than except Exception) so a cancellation
        # (asyncio.CancelledError, a BaseException, not an Exception) also
        # triggers cleanup of whatever was uploaded before the cancellation
        # landed (review round 1, item 4) — finally always runs, and simply
        # not raising here lets the cancellation propagate on its own.
        if not turn_succeeded:
            # Shielded: if the caller cancels *again* while this cleanup is
            # in flight (e.g. a second Ctrl-C / stream-abort racing the
            # first), only this `await` is interrupted — the cleanup
            # coroutine itself keeps running as a detached task rather than
            # being torn down half-finished, so files already removed stay
            # removed and the rest still get a chance to finish.
            await asyncio.shield(
                _cleanup_turn_refs(
                    fms,
                    new_refs,
                    agent_id=snapshot.agent_id,
                    user_context=user_context,
                    conversation_id=conversation_id,
                )
            )

    merged_refs = list(new_refs)
    seen_ids = {ref.file_id for ref in new_refs}
    for ref in existing_refs:
        if ref.file_id not in seen_ids:
            merged_refs.append(ref)
            seen_ids.add(ref.file_id)

    text = "\n\n".join(segment for segment in text_segments if segment)
    return TurnInputs(text=text, file_refs=merged_refs)


async def cleanup(fms: FileManagementService, refs: Sequence[FileReference]) -> None:
    """Release this turn's ephemeral uploads once the turn is done.

    Thin wrapper around ``FileManagementService.cleanup_ephemeral_refs``,
    mirroring the ``finally``-block cleanup in ``routers/public/v1/chat.py``.
    Persistent uploads (agent with memory + conversation_id) are left alone:
    this is the *successful*-turn path, where they are meant to stick around.
    """
    await fms.cleanup_ephemeral_refs(list(refs))
