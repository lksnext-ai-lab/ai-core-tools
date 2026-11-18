"""Failure logging for agent turns that must never write message content to the logs.

A provider error text can echo the prompt, and so can the message line of a traceback (also of
chained ``__cause__`` / ``__context__`` exceptions). The flexible App chat therefore logs only
the exception class names, ids, a short correlation id and the traceback *frames* (file, line,
function and source line carry code, never exception messages). Every other channel (playground,
public API, ...) logs exactly as before. The same class chain + correlation id is what a Chat turn
stores as its metrics ``error_message`` (see :func:`chat_failure_summary`), so a dashboard entry can be
matched to its log line.
"""
from __future__ import annotations

import logging
import traceback
import uuid
from typing import Optional

_MAX_CHAIN = 8
_MAX_FRAMES = 50
_CORRELATION_ATTR = "_chat_correlation_id"


class SafeText(str):
    """Marker: a text built only from class names / ids, safe to store for a Chat turn."""


def _chain(exc: BaseException) -> list[BaseException]:
    """``exc`` followed by its ``__cause__`` / ``__context__`` chain (bounded, cycle-safe)."""
    seen: list[BaseException] = []
    current: Optional[BaseException] = exc
    while current is not None and len(seen) < _MAX_CHAIN and not any(current is s for s in seen):
        seen.append(current)
        nxt = current.__cause__
        current = nxt if nxt is not None else current.__context__
    return seen


def chain_names(exc: BaseException) -> str:
    """``"RuntimeError <- ValueError"``: the exception class names of the chain, never any text."""
    return " <- ".join(type(item).__name__ for item in _chain(exc))


def safe_traceback(exc: BaseException) -> str:
    """Traceback frames of ``exc`` and its chain, WITHOUT any exception message."""
    parts = []
    for item in reversed(_chain(exc)):
        frames = "".join(traceback.format_tb(item.__traceback__, limit=_MAX_FRAMES))
        parts.append(f"{type(item).__name__}:\n{frames}" if frames else f"{type(item).__name__}\n")
    return "".join(parts)


def correlation_id_of(exc: BaseException) -> str:
    """Short id of this failure; stable for the same exception object (set once, reused by every site)."""
    existing = getattr(exc, _CORRELATION_ATTR, None) if not isinstance(exc, type) else None
    if isinstance(existing, str):
        return existing
    new = uuid.uuid4().hex[:8]
    try:
        setattr(exc, _CORRELATION_ATTR, new)
    except Exception:  # noqa: BLE001 - exceptions with __slots__: the id then differs per site
        pass
    return new


def chat_failure_summary(exc: BaseException) -> SafeText:
    """What a Chat turn stores instead of ``str(exc)``: the class chain and the log correlation id."""
    try:
        return SafeText(f"{chain_names(exc)} correlation_id={correlation_id_of(exc)}")
    except Exception:  # noqa: BLE001 - never raise from failure handling
        return SafeText("<unloggable> correlation_id=unknown")


def log_turn_failure(
    log: logging.Logger,
    what: str,
    exc: BaseException,
    *,
    chat_turn: bool,
    agent_id: Optional[int] = None,
    conversation_id: Optional[int] = None,
    level: int = logging.ERROR,
) -> Optional[str]:
    """Log a failed turn. Returns the correlation id for a chat turn, else None. Never raises.

    Non-chat turns: ``"<what>: <exc text>"`` with the full traceback (``exc_info``), as always (the
    record's source location is the caller's, via ``stacklevel=2``).
    Chat turns: exception class names, ``agent_id``, ``conversation_id``, a correlation id and the
    message-free frames; never ``str(exc)`` nor ``exc_info``.
    """
    if not chat_turn:
        try:
            log.log(level, "%s: %s", what, str(exc), exc_info=True, stacklevel=2)
        except Exception:  # noqa: BLE001 - e.g. an exception whose __str__ raises
            try:
                log.log(level, "%s: <unloggable %s>", what, type(exc).__name__, stacklevel=2)
            except Exception:  # noqa: BLE001
                pass
        return None
    correlation_id = correlation_id_of(exc)
    try:
        log.log(
            level,
            "%s (chat turn): exception=%s agent_id=%s conversation_id=%s correlation_id=%s\n%s",
            what, chain_names(exc), agent_id, conversation_id, correlation_id, safe_traceback(exc),
            stacklevel=2,
        )
    except Exception:  # noqa: BLE001
        try:
            log.log(level, "%s (chat turn): <unloggable> correlation_id=%s", what, correlation_id, stacklevel=2)
        except Exception:  # noqa: BLE001
            pass
    return correlation_id
