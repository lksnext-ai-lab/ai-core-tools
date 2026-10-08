"""Centralized A2A (Agent2Agent protocol) environment configuration.

See plan.md AD-15: every A2A env var is read here, and nowhere else. The module
exposes a frozen :class:`A2AConfig` dataclass plus a process-wide, cached
:func:`get_a2a_config`. Parsing is defensive: a malformed value never raises,
it falls back to the documented default and logs one warning.

Tests that mutate env vars between cases must call ``get_a2a_config.cache_clear()``.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional
from urllib.parse import quote, urlsplit

from utils.logger import get_logger

logger = get_logger(__name__)

_TRUTHY = {"true", "1", "yes", "on"}
_FALSY = {"false", "0", "no", "off"}

# "slug/id": the app slug charset mirrors the one enforced for App/MCPServer
# slugs elsewhere in the codebase (``^[a-z0-9-]+$``), the id is a positive int.
_ROOT_AGENT_PATTERN = re.compile(r"^[a-z0-9-]+/\d+$")

_VALID_URL_SCHEMES = {"http", "https"}


def _get_bool(name: str, default: bool) -> bool:
    """Parse a boolean env var; malformed values fall back to ``default`` with a warning."""
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUTHY:
        return True
    if value in _FALSY:
        return False
    logger.warning("Invalid boolean for %s=%r; using default %s", name, raw, default)
    return default


def _get_int(
    name: str, default: int, *, min_value: Optional[int] = None, max_value: Optional[int] = None
) -> int:
    """Parse an int env var; malformed or out-of-[``min_value``, ``max_value``] values fall back to ``default``."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw.strip())
    except (TypeError, ValueError):
        logger.warning("Invalid integer for %s=%r; using default %s", name, raw, default)
        return default
    if min_value is not None and value < min_value:
        logger.warning(
            "%s=%s is below the minimum %s; using default %s", name, value, min_value, default
        )
        return default
    if max_value is not None and value > max_value:
        logger.warning(
            "%s=%s is above the maximum %s; using default %s", name, value, max_value, default
        )
        return default
    return value


def _get_float(
    name: str, default: float, *, min_value: Optional[float] = None, exclusive: bool = False
) -> float:
    """Parse a float env var; malformed, non-finite or out-of-range values fall back to ``default``."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw.strip())
    except (TypeError, ValueError):
        logger.warning("Invalid float for %s=%r; using default %s", name, raw, default)
        return default
    if not math.isfinite(value):
        logger.warning("Non-finite float for %s=%r; using default %s", name, raw, default)
        return default
    if min_value is not None:
        below = value <= min_value if exclusive else value < min_value
        if below:
            logger.warning(
                "%s=%s is %s the minimum %s; using default %s",
                name, value, "at or below" if exclusive else "below", min_value, default,
            )
            return default
    return value


def _get_root_agent(name: str = "A2A_ROOT_AGENT") -> Optional[str]:
    """Parse ``A2A_ROOT_AGENT``; a malformed value becomes ``None`` with a warning."""
    raw = os.getenv(name)
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    if not _ROOT_AGENT_PATTERN.match(raw):
        logger.warning("Malformed %s=%r (expected 'slug/id'); ignoring", name, raw)
        return None
    return raw


def _parse_public_base_url(name: str = "A2A_PUBLIC_BASE_URL") -> Optional[str]:
    """Parse and validate ``A2A_PUBLIC_BASE_URL``.

    Must be ``http(s)://host[:port][/path]`` with no query string or fragment
    (it is a base to concatenate onto, not a full URL). Returns ``None`` — with
    a warning — for anything else, including an unset/empty value.
    """
    raw = os.getenv(name)
    if not raw:
        return None
    stripped = raw.strip().rstrip("/")
    if not stripped:
        return None

    parts = urlsplit(stripped)
    if parts.scheme not in _VALID_URL_SCHEMES:
        logger.warning(
            "Malformed %s=%r (scheme must be http or https); ignoring", name, raw
        )
        return None
    if not parts.netloc:
        logger.warning("Malformed %s=%r (missing host); ignoring", name, raw)
        return None
    if parts.query or parts.fragment:
        logger.warning(
            "Malformed %s=%r (must not include a query string or fragment); ignoring", name, raw
        )
        return None
    return stripped


@dataclass(frozen=True)
class A2AConfig:
    """Resolved A2A environment configuration (AD-15). Immutable; use get_a2a_config()."""

    enabled: bool
    enable_v0_3_compat: bool
    root_agent: Optional[str]
    public_base_url: Optional[str]
    discovery_rate_limit_per_minute: int
    max_request_mb: int
    max_file_mb: int
    inline_file_max_bytes: int
    file_url_ttl_seconds: int
    uri_fetch_timeout_seconds: int
    task_retention_days: int
    task_timeout_seconds: int
    turn_max_seconds: int
    sweep_interval_seconds: int
    event_poll_seconds: float
    stream_coalesce_ms: int
    keepalive_seconds: float
    purge_grace_seconds: int
    status_updates: bool
    sdk_debug: bool
    max_parts: int
    max_file_parts: int
    stream_max_seconds: int
    stream_liveness_seconds: float
    max_concurrent_streams_per_app: int
    max_concurrent_streams_per_key: int
    max_concurrent_streams_worker: int
    rpc_preauth_rate_limit_per_minute: int
    non_send_max_body_bytes: int


@lru_cache(maxsize=1)
def get_a2a_config() -> A2AConfig:
    """Return the process-wide A2A config, reading env vars once (cached).

    Tests that change env vars must call ``get_a2a_config.cache_clear()`` first.
    """
    base_url = _parse_public_base_url()
    if not base_url and not os.getenv("FRONTEND_URL"):
        # Logged once per cache lifetime: public_base_url() would otherwise fall
        # back to the inbound request's Host header, which an untrusted proxy
        # can spoof — unsafe for a card that may get cached/shared.
        logger.warning(
            "Neither A2A_PUBLIC_BASE_URL nor FRONTEND_URL is set; A2A card/RPC URLs "
            "will fall back to the request's Host header, which is unsafe for cached "
            "cards if that header isn't trustworthy behind your reverse proxy."
        )

    return A2AConfig(
        enabled=_get_bool("A2A_ENABLED", True),
        enable_v0_3_compat=_get_bool("A2A_ENABLE_V0_3_COMPAT", True),
        root_agent=_get_root_agent(),
        public_base_url=base_url,
        # 0 is a legitimate "unlimited" value for the discovery limiter, mirroring
        # the convention used by the other rate limiters in routers/controls/.
        discovery_rate_limit_per_minute=_get_int("A2A_DISCOVERY_RATE_LIMIT_PER_MINUTE", 60),
        max_request_mb=_get_int("A2A_MAX_REQUEST_MB", 32, min_value=1),
        max_file_mb=_get_int("A2A_MAX_FILE_MB", 10, min_value=1),
        inline_file_max_bytes=_get_int("A2A_INLINE_FILE_MAX_BYTES", 5242880, min_value=1),
        # Capped at 24h (fix round 1, item 10): an unbounded TTL would let a
        # single signed output-file URL (AD-12) stay valid indefinitely if an
        # operator fat-fingers this env var, defeating the whole point of an
        # *expiring* signature.
        file_url_ttl_seconds=_get_int("A2A_FILE_URL_TTL_SECONDS", 3600, min_value=1, max_value=86400),
        uri_fetch_timeout_seconds=_get_int("A2A_URI_FETCH_TIMEOUT_SECONDS", 15, min_value=1),
        task_retention_days=_get_int("A2A_TASK_RETENTION_DAYS", 30, min_value=1),
        task_timeout_seconds=_get_int("A2A_TASK_TIMEOUT_SECONDS", 900, min_value=1),
        # Fix round 1, item 2 (RB-2 bridge side): a hard wall-clock cap on one
        # A2A turn's streaming section, independent of `task_timeout_seconds`
        # (which is the *sweep*'s staleness threshold for a worker-crash/
        # restart scenario, step_018 -- a different failure mode with a
        # different owner). Same default as a reasonable starting point; the
        # two are intentionally separately configurable.
        turn_max_seconds=_get_int("A2A_TURN_MAX_SECONDS", 900, min_value=1),
        sweep_interval_seconds=_get_int("A2A_SWEEP_INTERVAL_SECONDS", 600, min_value=1),
        event_poll_seconds=_get_float("A2A_EVENT_POLL_SECONDS", 0.5, min_value=0, exclusive=True),
        # 0ms is a legitimate "coalescing disabled" value.
        stream_coalesce_ms=_get_int("A2A_STREAM_COALESCE_MS", 250),
        keepalive_seconds=_get_float("A2A_KEEPALIVE_SECONDS", 1.0, min_value=0, exclusive=True),
        # 0s is a legitimate "no grace period" value.
        purge_grace_seconds=_get_int("A2A_PURGE_GRACE_SECONDS", 5),
        status_updates=_get_bool("A2A_STATUS_UPDATES", False),
        sdk_debug=_get_bool("A2A_SDK_DEBUG", False),
        # Input-processing caps (FR-18/NFR-5): bound how much work a single
        # inbound Message can make the server do before any fetch/upload runs.
        max_parts=_get_int("A2A_MAX_PARTS", 64, min_value=1),
        max_file_parts=_get_int("A2A_MAX_FILE_PARTS", 10, min_value=1),
        # RB-2 (step_017 router): a hard wall-clock cap on how long the router
        # keeps a SubscribeToTask/SendStreamingMessage SSE response open, plus
        # how often it re-checks task liveness via `store.get` while waiting
        # for the next event -- independent of `turn_max_seconds` (the
        # bridge's own cap on *producing* events) because a remote tail
        # (another worker owns the task) has no bridge of its own driving it
        # and would otherwise poll forever once the owning worker is gone.
        stream_max_seconds=_get_int("A2A_STREAM_MAX_SECONDS", 1800, min_value=1),
        stream_liveness_seconds=_get_float(
            "A2A_STREAM_LIVENESS_SECONDS", 5.0, min_value=0, exclusive=True
        ),
        # RB-3 (step_017 router): bulkhead caps on concurrent SSE streams.
        # 0 means unlimited for the per-app/per-key counters, mirroring the
        # convention used by the other limiters in routers/controls/. The
        # per-*worker* cap has no "unlimited" value -- it bounds a plain
        # `asyncio.BoundedSemaphore` sized once at process start -- and its
        # default (40) is deliberately well under uvicorn's own
        # `--limit-concurrency` default (100, see `UVICORN_LIMIT_CONCURRENCY`
        # below): every A2A stream also holds one of uvicorn's own concurrent
        # connection slots, and a worker-level cap at or above that figure
        # could never actually bind -- uvicorn would already be rejecting new
        # connections first. `_clamp_worker_cap` enforces this at resolution
        # time (fix round 1, HIGH-3), not just in the default.
        max_concurrent_streams_per_app=_get_int(
            "A2A_MAX_CONCURRENT_STREAMS_PER_APP", 10, min_value=0
        ),
        max_concurrent_streams_per_key=_get_int(
            "A2A_MAX_CONCURRENT_STREAMS_PER_KEY", 5, min_value=0
        ),
        max_concurrent_streams_worker=_clamp_worker_cap(
            _get_int("A2A_MAX_CONCURRENT_STREAMS_WORKER", 40, min_value=1)
        ),
        # MEDIUM-7 (fix round 1): a target-independent, per-IP limiter that
        # runs before any DB/auth work on the RPC route -- generous on
        # purpose (it is not meant to replace the per-app `agent_rate_limit`
        # budget, only to bound raw request volume from one caller).
        rpc_preauth_rate_limit_per_minute=_get_int(
            "A2A_RPC_PREAUTH_RATE_LIMIT_PER_MINUTE", 300
        ),
        # MEDIUM-8 (fix round 1): methods other than SendMessage/
        # SendStreamingMessage carry no message payload worth megabytes --
        # GetTask/CancelTask/SubscribeToTask/GetExtendedAgentCard/etc. need at
        # most a short id. 64 KiB leaves generous room for a pathological but
        # legitimate `params` dict without allowing a non-send call to pay the
        # full `A2A_MAX_REQUEST_MB` cost.
        non_send_max_body_bytes=_get_int(
            "A2A_NON_SEND_MAX_BODY_BYTES", 65536, min_value=1
        ),
    )


def _clamp_worker_cap(configured: int) -> int:
    """Clamps the per-worker stream cap below uvicorn's `--limit-concurrency` (HIGH-3).

    Every concurrent A2A SSE stream also occupies one of uvicorn's own
    concurrent-connection slots (`--limit-concurrency`, default 100, read here
    from `UVICORN_LIMIT_CONCURRENCY` -- uvicorn itself has no env var for this
    flag, so the deployment's entrypoint/compose file must export it to match
    whatever `--limit-concurrency` it actually passes). A worker-level stream
    cap at or above that figure can never actually bind: uvicorn would already
    be refusing new connections before this bulkhead ever saw them, and in the
    meantime it silently starves every *other* route this worker serves.
    """
    limit_concurrency = _get_int("UVICORN_LIMIT_CONCURRENCY", 100, min_value=1)
    if configured >= limit_concurrency:
        clamped = max(1, limit_concurrency - 1)
        logger.warning(
            "A2A_MAX_CONCURRENT_STREAMS_WORKER=%s is >= UVICORN_LIMIT_CONCURRENCY=%s; "
            "clamping to %s. Streams share uvicorn's own connection-concurrency budget "
            "with every other route.",
            configured, limit_concurrency, clamped,
        )
        return clamped
    return configured


def public_base_url(request_base_url: Optional[str] = None) -> Optional[str]:
    """Resolve the public base URL (FR-11).

    Order: ``A2A_PUBLIC_BASE_URL`` env var, then ``FRONTEND_URL`` env var, then the
    caller-supplied request base URL. Returns ``None`` if none are available.
    The trailing slash is always stripped.
    """
    config = get_a2a_config()
    if config.public_base_url:
        return config.public_base_url

    frontend_url = os.getenv("FRONTEND_URL")
    if frontend_url:
        frontend_url = frontend_url.strip().rstrip("/")
        if frontend_url:
            return frontend_url

    if request_base_url:
        request_base_url = request_base_url.strip().rstrip("/")
        if request_base_url:
            return request_base_url

    return None


def agent_rpc_url(base: str, app_slug: str, agent_id: int) -> str:
    """Build the absolute per-agent JSON-RPC endpoint URL."""
    return f"{base.rstrip('/')}/a2a/v1/apps/{quote(app_slug, safe='')}/agents/{agent_id}"


def agent_card_url(base: str, app_slug: str, agent_id: int) -> str:
    """Build the absolute per-agent well-known agent-card URL."""
    return f"{agent_rpc_url(base, app_slug, agent_id)}/.well-known/agent-card.json"


def effective_max_file_bytes(app_max_file_size_mb: Optional[int]) -> int:
    """Return the effective per-file byte cap.

    Uses the app's ``max_file_size_mb`` when it is set and > 0, else the
    ``A2A_MAX_FILE_MB`` env default.
    """
    config = get_a2a_config()
    if app_max_file_size_mb and app_max_file_size_mb > 0:
        return app_max_file_size_mb * 1024 * 1024
    return config.max_file_mb * 1024 * 1024
