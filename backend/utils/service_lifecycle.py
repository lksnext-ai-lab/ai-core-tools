"""End-of-service lifecycle of AI, embedding and sandbox services.

Pure module (no DB access) so it can be used from ``tools/``, ``utils/`` and ``services/``.
A service is *retired* once ``end_of_service_at`` has passed, whatever the warning window
is, so runtime guards need no settings; the warning window only decides between
*active* and *deprecated* for display.
"""

from contextlib import contextmanager
import unicodedata
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, Iterator, Optional

from utils.error_handlers import AppError
from utils.logger import get_logger

logger = get_logger(__name__)

SERVICE_KIND_AI = "ai"
SERVICE_KIND_EMBEDDING = "embedding"
SERVICE_KIND_SANDBOX = "sandbox"

_UNKNOWN = "unknown"

MAX_DEPRECATION_NOTICE_LENGTH = 1000
_NOTICE_REPLACED_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp"})


class LifecycleStatus(str, Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


def to_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Naive datetimes are taken as UTC; aware ones are converted to UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def normalize_deprecation_notice(value: Optional[str]) -> Optional[str]:
    """Clean an admin-authored deprecation notice.

    Control and invisible formatting characters (Unicode categories Cc: CR, LF, tab, NUL; Cf: bidi
    overrides, zero-width; Zl/Zp: U+2028/9) become a space so a notice cannot forge lines in logs; the result is stripped, empty -> ``None``.

    Raises:
        ValueError: if the cleaned notice is longer than 1000 characters.
    """
    if value is None:
        return None
    cleaned = "".join(" " if unicodedata.category(ch) in _NOTICE_REPLACED_CATEGORIES else ch for ch in str(value)).strip()
    if not cleaned:
        return None
    if len(cleaned) > MAX_DEPRECATION_NOTICE_LENGTH:
        raise ValueError(f"deprecation_notice must be at most {MAX_DEPRECATION_NOTICE_LENGTH} characters")
    return cleaned


def compute_lifecycle_status(
    end_of_service_at: Optional[datetime],
    warning_days: int,
    now: Optional[datetime] = None,
) -> LifecycleStatus:
    """Status at ``now`` (default: current UTC time). ``warning_days`` <= 0 means no deprecated phase."""
    eos = to_utc(end_of_service_at)
    if eos is None:
        return LifecycleStatus.ACTIVE
    current = to_utc(now) or datetime.now(timezone.utc)
    if current >= eos:
        return LifecycleStatus.RETIRED
    if eos - current <= timedelta(days=max(warning_days, 0)):
        return LifecycleStatus.DEPRECATED
    return LifecycleStatus.ACTIVE


def is_retired(service: Any, now: Optional[datetime] = None) -> bool:
    """True when ``service`` has passed its end of service.

    Uses ``getattr`` so transient objects without lifecycle attributes (e.g. the mock
    services built by test-connection) are never blocked.
    """
    eos = getattr(service, "end_of_service_at", None)
    if eos is None:
        return False
    return compute_lifecycle_status(eos, 0, now) is LifecycleStatus.RETIRED


def _with_notice(message: str, notice: Optional[str]) -> str:
    return f"{message} {notice}" if notice else message


def _retired_on(name: str, eos: datetime) -> str:
    return f"Service {name} was retired on {to_utc(eos):%Y-%m-%d}."


def ai_retired_message(name: str, eos: datetime, notice: Optional[str] = None) -> str:
    return _with_notice(_retired_on(name, eos), notice)


def embedding_retired_message(name: str, eos: datetime, notice: Optional[str] = None) -> str:
    return _with_notice(
        f"{_retired_on(name, eos)} Silos using it must be re-indexed with another embedding service.", notice
    )


def sandbox_retired_message(name: str, eos: datetime, notice: Optional[str] = None) -> str:
    return _with_notice(
        f"{_retired_on(name, eos)} The code interpreter is disabled until another sandbox service is selected.",
        notice,
    )


_MESSAGE_BUILDERS = {
    SERVICE_KIND_AI: ai_retired_message,
    SERVICE_KIND_EMBEDDING: embedding_retired_message,
    SERVICE_KIND_SANDBOX: sandbox_retired_message,
}


class ServiceRetiredError(AppError):
    """A retired service was used. Mapped to 409 ``SERVICE_RETIRED`` at the HTTP edge."""

    def __init__(self, service: Any, kind: str):
        self.service_id = getattr(service, "service_id", None)
        self.service_name = getattr(service, "name", None) or _UNKNOWN
        self.kind = kind
        self.end_of_service_at = to_utc(getattr(service, "end_of_service_at", None))
        self.deprecation_notice = getattr(service, "deprecation_notice", None)
        build = _MESSAGE_BUILDERS.get(kind, ai_retired_message)
        message = build(self.service_name, self.end_of_service_at, self.deprecation_notice)
        super().__init__(message, "SERVICE_RETIRED", 409)


# Who is making the call, for the log line of a blocked call.
_call_context: ContextVar[Optional[Dict[str, Any]]] = ContextVar("service_call_context", default=None)


def set_service_call_context(
    *,
    channel: str,
    app_id: Optional[int] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[Any] = None,
) -> None:
    """Record the caller for the current context.

    Plain ``ContextVar.set``: safe in request tasks and async generators, because each
    request/stream task runs in its own context copy. Never reset it across a ``yield``;
    sync/background code should use ``service_call_context`` instead.
    """
    _call_context.set(
        {"channel": channel, "app_id": app_id, "resource_type": resource_type, "resource_id": resource_id}
    )


@contextmanager
def service_call_context(
    *,
    channel: str,
    app_id: Optional[int] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[Any] = None,
) -> Iterator[None]:
    """Set the call context for a block and restore the previous one on exit."""
    token = _call_context.set(
        {"channel": channel, "app_id": app_id, "resource_type": resource_type, "resource_id": resource_id}
    )
    try:
        yield
    finally:
        _call_context.reset(token)


def agent_turn_context_kwargs(channel: Any, user_context: Optional[Dict[str, Any]], agent_id: Any) -> Dict[str, Any]:
    """Keyword arguments for ``set_service_call_context`` / ``service_call_context`` of an agent chat turn.

    ``channel`` may be an enum (its ``.value`` is used) or a string. A scheduled-task run is
    reported as the task, anything else as the agent.
    """
    ctx = user_context or {}
    task_id = ctx.get("scheduled_task_id")
    return {
        "channel": getattr(channel, "value", channel),
        "app_id": ctx.get("app_id"),
        "resource_type": "scheduled_task" if task_id is not None else "agent",
        "resource_id": task_id if task_id is not None else agent_id,
    }


def get_service_call_context() -> Dict[str, Any]:
    """Current call context (empty dict when none was set)."""
    return dict(_call_context.get() or {})


def ensure_service_active(service: Any, kind: str) -> None:
    """Raise ``ServiceRetiredError`` if ``service`` is retired, logging one structured WARNING.

    Callers that catch the error must not log it again.
    """
    if service is None or not is_retired(service):
        return
    ctx = get_service_call_context()

    def _field(key: str) -> Any:
        value = ctx.get(key)
        return _UNKNOWN if value is None else value

    logger.warning(
        "service_lifecycle.blocked service_id=%s service_app_id=%s kind=%s app_id=%s channel=%s "
        "resource_type=%s resource_id=%s",
        getattr(service, "service_id", None),
        getattr(service, "app_id", None),
        kind,
        _field("app_id"),
        _field("channel"),
        _field("resource_type"),
        _field("resource_id"),
    )
    raise ServiceRetiredError(service, kind)


class RetiredServiceAssignmentError(ValueError):
    """A retired service was chosen for a field where it was not already selected."""


def ensure_assignable(service: Any, current_id: Optional[int], field_label: str, kind: str) -> None:
    """Reject newly assigning a retired service; keeping the current (retired) one is fine."""
    if service is None or not is_retired(service):
        return
    if getattr(service, "service_id", None) == current_id:
        return
    eos = to_utc(getattr(service, "end_of_service_at", None))
    raise RetiredServiceAssignmentError(
        f"{field_label}: service {getattr(service, 'name', _UNKNOWN)} was retired on {eos:%Y-%m-%d} "
        "and cannot be selected."
    )
