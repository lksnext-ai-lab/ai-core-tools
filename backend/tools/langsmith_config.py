"""Centralized LangSmith / tracing configuration for MattinAI.

Resolves per-App or global env-fallback settings, caches LangSmith clients,
validates API keys using the public SDK, and builds enriched RunnableConfig
overrides (run_name, metadata, tags) for LangChain 1.x / LangGraph 1.x.

The canonical LangChain 1.x pattern for per-tenant tracing is:

    tracer = LangChainTracer(client=ls_client, project_name="my-project")
    await chain.ainvoke(
        input,
        config={
            "callbacks": [tracer],
            "metadata": {...},
            "tags": [...],
            "run_name": "...",
        },
    )

`langsmith.tracing_context` is NOT used here — that context manager is
designed for `@traceable` decorated functions, not LangGraph runnables.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional, Sequence, Tuple

import langsmith as ls
from langchain_core.tracers.langchain import LangChainTracer

from utils.logger import get_logger

logger = get_logger(__name__)


DEFAULT_LANGSMITH_ENDPOINT = "https://api.smith.langchain.com"
_TRUTHY_VALUES = {"true", "1", "on", "yes"}


@dataclass(frozen=True)
class LangSmithSettings:
    """Resolved LangSmith configuration for a single agent invocation."""

    api_key: str
    project_name: str
    endpoint: str
    source: Literal["app", "env"]


ValidationStatus = Literal["ok", "unauthorized", "network", "unknown"]


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of a LangSmith API-key validation call."""

    valid: bool
    status: ValidationStatus
    message: str


# ---------------------------------------------------------------------------
# Client cache
# ---------------------------------------------------------------------------

# Maps (api_key_hash, endpoint) -> ls.Client. We hash the key so the cache
# key never holds raw credentials in memory longer than necessary.
_client_cache: Dict[Tuple[str, str], ls.Client] = {}
# Reverse index app_id -> cache key, populated by callers via remember_app_client.
_app_to_cache_key: Dict[int, Tuple[str, str]] = {}


def _cache_key(api_key: str, endpoint: str) -> Tuple[str, str]:
    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    return digest, endpoint


def get_langsmith_client(api_key: str, endpoint: str = DEFAULT_LANGSMITH_ENDPOINT) -> ls.Client:
    """Return a cached LangSmith client for the given credentials."""
    key = _cache_key(api_key, endpoint)
    client = _client_cache.get(key)
    if client is None:
        client = ls.Client(api_key=api_key, api_url=endpoint)
        _client_cache[key] = client
    return client


def remember_app_client(app_id: int, api_key: str, endpoint: str) -> None:
    """Track which cache entry belongs to an app so we can invalidate later."""
    _app_to_cache_key[app_id] = _cache_key(api_key, endpoint)


def clear_client_cache(app_id: Optional[int] = None) -> None:
    """Invalidate cached clients.

    Args:
        app_id: When supplied, drops only the client bound to that app. When
            ``None``, clears every cached client (used at shutdown).
    """
    if app_id is None:
        _client_cache.clear()
        _app_to_cache_key.clear()
        return

    key = _app_to_cache_key.pop(app_id, None)
    if key is not None:
        _client_cache.pop(key, None)


def flush_langsmith_clients() -> None:
    """Flush every cached client. Called from the FastAPI shutdown hook.

    LangSmith batches trace uploads; flushing ensures pending traces are
    transmitted before the process exits.
    """
    for client in list(_client_cache.values()):
        try:
            client.flush()
        except Exception as exc:  # noqa: BLE001 — best-effort flush
            logger.warning("LangSmith client flush failed: %s", exc)


# ---------------------------------------------------------------------------
# Settings resolution
# ---------------------------------------------------------------------------

def _env_tracing_enabled() -> bool:
    return os.getenv("LANGSMITH_TRACING", "").strip().lower() in _TRUTHY_VALUES


def resolve_langsmith_settings(app) -> Optional[LangSmithSettings]:
    """Resolve effective LangSmith settings for the given App.

    Resolution order:
      1. ``App.langsmith_api_key`` if set → use it with ``project_name = app.name``.
      2. Else, if ``LANGSMITH_TRACING`` is truthy and ``LANGSMITH_API_KEY`` is
         set → use those env vars as a global fallback.
      3. Else, return ``None`` (tracing disabled, no error).

    Args:
        app: An ``App`` ORM instance (must expose ``app_id``, ``name``,
            ``langsmith_api_key``).
    """
    app_key = (getattr(app, "langsmith_api_key", "") or "").strip()
    if app_key:
        endpoint = (os.getenv("LANGSMITH_ENDPOINT") or DEFAULT_LANGSMITH_ENDPOINT).strip()
        remember_app_client(app.app_id, app_key, endpoint)
        return LangSmithSettings(
            api_key=app_key,
            project_name=app.name or f"app-{app.app_id}",
            endpoint=endpoint,
            source="app",
        )

    if not _env_tracing_enabled():
        return None

    env_key = (os.getenv("LANGSMITH_API_KEY") or "").strip()
    if not env_key:
        return None

    endpoint = (os.getenv("LANGSMITH_ENDPOINT") or DEFAULT_LANGSMITH_ENDPOINT).strip()
    project = (os.getenv("LANGSMITH_PROJECT") or "default").strip()
    return LangSmithSettings(
        api_key=env_key,
        project_name=project,
        endpoint=endpoint,
        source="env",
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_langsmith_key(
    api_key: str,
    endpoint: str = DEFAULT_LANGSMITH_ENDPOINT,
) -> ValidationResult:
    """Validate a LangSmith API key against the live API.

    Calls ``Client.info`` (which maps to ``GET /info``) — this is the most
    permissive public endpoint and is reachable by any authenticated key
    regardless of its scopes. We deliberately avoid endpoints like
    ``list_runs`` or ``list_projects`` because **write-only** service keys
    return 403 there even though they can perfectly ingest traces — and that
    is the only capability MattinAI needs.

    Returns a ``ValidationResult`` describing the outcome — never raises.
    """
    api_key = (api_key or "").strip()
    if not api_key:
        return ValidationResult(
            valid=False,
            status="unauthorized",
            message="Empty API key",
        )

    try:
        client = get_langsmith_client(api_key, endpoint)
        info = client.info
        if info is None:
            return ValidationResult(
                valid=False,
                status="unknown",
                message="LangSmith /info returned an empty response",
            )
        return ValidationResult(
            valid=True,
            status="ok",
            message="LangSmith API key validated",
        )
    except Exception as exc:  # noqa: BLE001 — classify any failure mode
        message = str(exc)
        lowered = message.lower()
        # /info returns 401 for an unknown or revoked key. 403 here is rare
        # because /info is the most permissive endpoint, but treat it the
        # same: the key is reaching LangSmith but not accepted.
        if "401" in lowered or "unauthorized" in lowered:
            return ValidationResult(
                valid=False,
                status="unauthorized",
                message="API key is invalid, revoked, or expired",
            )
        if "403" in lowered or "forbidden" in lowered:
            return ValidationResult(
                valid=False,
                status="unauthorized",
                message="API key was rejected by LangSmith (forbidden on /info)",
            )
        if (
            "timeout" in lowered
            or "connection" in lowered
            or "name or service" in lowered
            or "max retries" in lowered
            or "network" in lowered
        ):
            return ValidationResult(
                valid=False,
                status="network",
                message="Could not reach LangSmith — check connectivity and endpoint",
            )
        return ValidationResult(
            valid=False,
            status="unknown",
            message=f"Unexpected validation error: {type(exc).__name__}",
        )


# ---------------------------------------------------------------------------
# Per-invocation tracing config
# ---------------------------------------------------------------------------

def build_tracing_config(
    settings: LangSmithSettings,
    *,
    agent,
    user_context: Optional[Dict[str, Any]] = None,
    conversation_id: Optional[int] = None,
    session_id: Optional[str] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
    extra_tags: Optional[Sequence[str]] = None,
) -> Tuple[LangChainTracer, Dict[str, Any]]:
    """Build the LangChainTracer and the RunnableConfig overrides for a turn.

    Returns:
        Tuple of ``(tracer, overrides)``. ``overrides`` is a dict with the
        following keys ready to be merged into the existing config:

          - ``run_name`` (str)
          - ``metadata`` (dict)
          - ``tags`` (list[str])

    ``extra_metadata`` is merged into ``metadata`` without overriding the standard keys (a
    clashing standard key wins); ``extra_tags`` are appended to ``tags``. Both must hold ids and
    names only, never secrets.

    The caller is responsible for appending ``tracer`` to
    ``config["callbacks"]`` and merging the overrides.
    """
    client = get_langsmith_client(settings.api_key, settings.endpoint)
    tracer = LangChainTracer(client=client, project_name=settings.project_name)

    user_ctx = user_context or {}
    metadata: Dict[str, Any] = {
        "agent_id": getattr(agent, "agent_id", None),
        "agent_name": getattr(agent, "name", None),
        "agent_type": getattr(agent, "type", None),
        "app_id": getattr(getattr(agent, "app", None), "app_id", None),
        "app_name": getattr(getattr(agent, "app", None), "name", None),
        "has_memory": bool(getattr(agent, "has_memory", False)),
        "user_id": user_ctx.get("user_id"),
        "user_email": user_ctx.get("email"),
        "conversation_id": conversation_id,
        "session_id": session_id,
        "tracing_source": settings.source,
    }
    if extra_metadata:
        metadata = {**extra_metadata, **{k: v for k, v in metadata.items() if v is not None}}
    # Strip None values — LangSmith UI is cleaner without them.
    metadata = {k: v for k, v in metadata.items() if v is not None}

    tags = [
        f"agent:{agent.agent_id}",
        f"app:{settings.project_name}",
    ]
    agent_type = getattr(agent, "type", None)
    if agent_type:
        tags.append(f"agent_type:{agent_type}")
        if agent_type == "ocr_agent":
            tags.append("ocr")

    if extra_tags:
        tags.extend(t for t in extra_tags if t not in tags)

    overrides: Dict[str, Any] = {
        "run_name": f"agent:{getattr(agent, 'name', None) or agent.agent_id}",
        "metadata": metadata,
        "tags": tags,
    }
    return tracer, overrides


def apply_tracing_to_config(
    config: Dict[str, Any],
    tracer: LangChainTracer,
    overrides: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge a tracer + overrides into an existing RunnableConfig dict.

    Mutates and returns ``config`` for convenience. Existing callbacks,
    metadata, and tags are preserved.
    """
    config.setdefault("callbacks", []).append(tracer)

    existing_metadata = config.get("metadata") or {}
    config["metadata"] = {**existing_metadata, **overrides.get("metadata", {})}

    existing_tags = config.get("tags") or []
    merged_tags = list({*existing_tags, *overrides.get("tags", [])})
    config["tags"] = merged_tags

    run_name = overrides.get("run_name")
    if run_name:
        config["run_name"] = run_name

    return config
