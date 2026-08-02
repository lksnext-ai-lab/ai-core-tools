"""
SandboxSessionService — manages SandboxHandle lifecycle per conversation.

A sandbox is keyed by ``session_key`` produced by the static helper
``SandboxSessionService.session_key(agent_id, conversation_id)``.  One active
handle is kept in memory per key; the underlying sandbox is created lazily on
first use and its state is persisted to ``Conversation.sandbox_state`` so that
server restarts can attempt to resume the same remote sandbox.

Open-question resolutions encoded here:

- Q2 (sandbox file scope): sandboxes are scoped to the conversation.
- Q5 (backend restart): ``Conversation.sandbox_session_id`` / ``sandbox_state``
  record provider state.  ``get_or_create`` loads this on cache miss and passes
  ``existing_sandbox_id`` to the provider so it can attempt a resume.

Reliability notes (sandbox-v2-core hardening):

- All DB persistence in this module goes through a dedicated, short-lived
  ``SessionLocal()`` — never through a caller-supplied ``Session``.  These
  lifecycle methods are invoked both from the request-serving thread (initial
  sandbox creation) and from LangChain tool-executor threads (``begin_use``/
  ``end_use`` wrapping REPL calls); SQLAlchemy ``Session`` objects are not
  thread-safe, so writing through the request-scoped session from a different
  thread risked corrupting its in-flight ORM state on the main chat path.
- Sandbox *creation* is serialized per ``session_key`` (see
  ``_creation_locks``) so two concurrent callers for the same key cannot both
  create a sandbox — the loser would otherwise be orphaned (never cached,
  never destroyed, but still billable on remote providers).
- A process-wide cap (``SANDBOX_MAX_CONCURRENT_SESSIONS``) bounds the number
  of live sandboxes so a single tenant cannot exhaust a shared sandbox host.
- Cleanup/reaper paths resolve the *tenant-specific* provider credentials
  (via the persisted ``sandbox_service_id``) before attempting a remote
  destroy, instead of a zero-credential provider instance, so destroy calls
  actually target the account/endpoint the sandbox was created on.
"""

from __future__ import annotations

import json
import threading
import time
import os
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, TYPE_CHECKING

from sqlalchemy.orm import Session

from utils.logger import get_logger
from tools.sandbox.provider import SandboxProvider, SandboxHandle, SandboxExpiredError

if TYPE_CHECKING:
    from models.conversation import Conversation

logger = get_logger(__name__)

_DEFAULT_CREATE_TIMEOUT_S = 60
_DEFAULT_IDLE_TIMEOUT_S = 120
_DEFAULT_REAP_INTERVAL_S = 30
_DEFAULT_MAX_CONCURRENT_SESSIONS = 50


class SandboxCapacityError(RuntimeError):
    """Raised when the global concurrent-sandbox cap has been reached.

    This is a process-wide cap (not per-app/per-tenant) intended to protect a
    shared sandbox host (e.g. a single OpenSandbox server) from being
    exhausted by one tenant opening many concurrent chats. Per-app quotas
    would require threading ``app_id`` through the session key, which is out
    of scope here. Configurable via the ``SANDBOX_MAX_CONCURRENT_SESSIONS``
    setting (see :func:`_max_concurrent_sessions`).
    """


def _create_timeout_s() -> int:
    try:
        return int(os.getenv("SANDBOX_CREATE_TIMEOUT_S", str(_DEFAULT_CREATE_TIMEOUT_S)))
    except (TypeError, ValueError):
        return _DEFAULT_CREATE_TIMEOUT_S


def _idle_timeout_s() -> int:
    """Return max idle time before a sandbox is stopped/destroyed."""
    try:
        import config as settings  # type: ignore[import]
        configured = int(getattr(settings, "SANDBOX_IDLE_TIMEOUT_S", _DEFAULT_IDLE_TIMEOUT_S))
    except Exception:
        configured = _DEFAULT_IDLE_TIMEOUT_S
    return max(1, configured)


def _reap_interval_s() -> int:
    """Return how often the background reaper should check idle sandboxes."""
    try:
        import config as settings  # type: ignore[import]
        configured = int(getattr(settings, "SANDBOX_REAPER_INTERVAL_S", _DEFAULT_REAP_INTERVAL_S))
    except Exception:
        configured = _DEFAULT_REAP_INTERVAL_S
    return max(1, min(configured, _idle_timeout_s()))


def _max_concurrent_sessions() -> int:
    """Return the process-wide cap on simultaneously live sandbox sessions.

    Configurable via ``SANDBOX_MAX_CONCURRENT_SESSIONS`` (read the same way as
    the other tunables in this module — no dedicated ``config.py`` entry is
    required; the default applies when unset).
    """
    try:
        import config as settings  # type: ignore[import]
        configured = int(
            getattr(settings, "SANDBOX_MAX_CONCURRENT_SESSIONS", _DEFAULT_MAX_CONCURRENT_SESSIONS)
        )
    except Exception:
        configured = _DEFAULT_MAX_CONCURRENT_SESSIONS
    return max(1, configured)


# ---------------------------------------------------------------------------
# DB state helpers (Phase 2)
# ---------------------------------------------------------------------------

@dataclass
class SavedSandboxState:
    """Deserialized snapshot of ``Conversation.sandbox_state``."""
    provider: str
    session_key: str
    sandbox_id: str
    updated_at: str
    created_at: str | None = None
    last_activity_at: str | None = None
    lease_expires_at: str | None = None
    idle_timeout_s: int | None = None
    sandbox_service_id: int | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _utc_now_iso() -> str:
    return _utc_now().isoformat() + "Z"


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.rstrip("Z"))
    except (ValueError, AttributeError):
        return None


def _state_activity_at(state: SavedSandboxState | None) -> datetime | None:
    if state is None:
        return None
    return _parse_utc(state.last_activity_at) or _parse_utc(state.updated_at)


def _load_sandbox_state(conversation: "Conversation | None") -> SavedSandboxState | None:
    """Deserialize ``Conversation.sandbox_state`` JSON.  Returns None if absent or unparseable."""
    if conversation is None:
        return None
    raw = getattr(conversation, "sandbox_state", None)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return SavedSandboxState(
            provider=data.get("provider", ""),
            session_key=data.get("session_key", ""),
            sandbox_id=data.get("sandbox_id", ""),
            updated_at=data.get("updated_at", ""),
            created_at=data.get("created_at"),
            last_activity_at=data.get("last_activity_at"),
            lease_expires_at=data.get("lease_expires_at"),
            idle_timeout_s=data.get("idle_timeout_s"),
            sandbox_service_id=data.get("sandbox_service_id"),
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def _state_is_idle_expired(state: SavedSandboxState | None) -> bool:
    """Return True if persisted sandbox state is older than the idle timeout."""
    if state is None:
        return False
    activity_at = _state_activity_at(state)
    if activity_at is None:
        return True
    lease_expires_at = _parse_utc(state.lease_expires_at)
    if lease_expires_at is not None and lease_expires_at >= _utc_now():
        return False
    return activity_at < (_utc_now() - timedelta(seconds=_idle_timeout_s()))


def _conversation_id_from_session_key(session_key: str) -> int | None:
    """Extract the conversation id from a conv_<agent_id>_<conversation_id> key."""
    parts = session_key.split("_", 2)
    if len(parts) != 3 or parts[0] != "conv":
        return None
    try:
        return int(parts[2])
    except (TypeError, ValueError):
        return None


def _resolve_conversation_id(
    conversation: "Conversation | None",
    session_key: str | None,
) -> int | None:
    """Resolve a Conversation id from either the ORM object or the session key.

    Prefers ``conversation.conversation_id`` when a loaded ``Conversation``
    object is available; falls back to parsing the stable
    ``conv_<agent_id>_<conversation_id>`` session key format used by
    REPL/tool-executor call sites that only have the key (no ORM object).
    """
    if conversation is not None:
        conv_id = getattr(conversation, "conversation_id", None)
        if conv_id is not None:
            return conv_id
    if session_key:
        return _conversation_id_from_session_key(session_key)
    return None


def _persist_sandbox_state(
    conversation: "Conversation | None",
    handle: SandboxHandle,
    *,
    db: Session | None = None,
    last_activity_at: str | None = None,
    lease_expires_at: str | None = None,
    sandbox_service_id: int | None = None,
) -> None:
    """Serialize *handle* into ``Conversation.sandbox_state`` and commit it.

    Always persists through a short-lived, dedicated ``SessionLocal()`` —
    NEVER through the caller-supplied *db* session. Sandbox lifecycle methods
    on this service are invoked both from the request-serving thread (initial
    creation) and from LangChain tool-executor threads (``begin_use``/
    ``end_use`` around REPL calls running on a different thread than the one
    that owns the request-scoped session). SQLAlchemy ``Session`` objects are
    not thread-safe, so writing through that session from another thread
    risks corrupting its in-flight ORM state. *db* is accepted only for
    call-site backward compatibility and is otherwise unused.

    The Conversation row to update is resolved by id — from
    ``conversation.conversation_id`` when a loaded ORM object is available,
    otherwise parsed from ``handle.session_key`` (the
    ``conv_<agent_id>_<conversation_id>`` format used by REPL tool call
    sites that only have the key).

    This is best-effort: any failure (unresolvable id, DB unavailable, no
    matching row) is logged at debug level and swallowed, since sandbox state
    persistence is an optimization (resume-after-restart) rather than a
    requirement for correctness of the current in-memory session.

    Args:
        conversation:       ORM ``Conversation`` object, if already loaded.
        handle:             The live sandbox handle to persist.
        db:                 Unused; retained for call-site compatibility.
        last_activity_at:   ISO timestamp of the activity that triggered this
                             persist. Defaults to "now" when omitted.
        lease_expires_at:   ISO timestamp until which the sandbox should be
                             considered actively leased (skips idle reaping).
        sandbox_service_id: The resolved ``SandboxService.service_id`` used to
                             create/own this sandbox, if any. Persisted so
                             cleanup/reaper paths can rebuild a
                             credential-bearing provider later. When omitted,
                             the previously persisted value (if any) is kept.
    """
    session_key = handle.session_key
    conversation_id = _resolve_conversation_id(conversation, session_key)
    if conversation_id is None:
        return

    try:
        from db.database import SessionLocal  # type: ignore[import]
        fresh_db = SessionLocal()
    except Exception as exc:
        logger.debug(
            "SandboxSessionService: cannot open DB session to persist sandbox state "
            "(conversation_id=%s): %s",
            conversation_id,
            exc,
            exc_info=True,
        )
        return

    try:
        from models.conversation import Conversation  # type: ignore[import]
        row = (
            fresh_db.query(Conversation)
            .filter(Conversation.conversation_id == conversation_id)
            .first()
        )
        if row is None:
            return

        existing = _load_sandbox_state(row)
        if session_key and existing is not None and existing.session_key and existing.session_key != session_key:
            # A different (newer/other) sandbox session already owns this
            # conversation's persisted state — never clobber it with a
            # stale/racing write from this handle.
            return
        if (
            session_key
            and getattr(row, "sandbox_session_id", None)
            and getattr(row, "sandbox_session_id", None) != handle.sandbox_id
            and existing is not None
            and existing.session_key != session_key
        ):
            return

        now = _utc_now_iso()
        state = {
            "provider": handle.provider_name,
            "session_key": handle.session_key,
            "sandbox_id": handle.sandbox_id,
            "sandbox_service_id": (
                sandbox_service_id
                if sandbox_service_id is not None
                else (existing.sandbox_service_id if existing is not None else None)
            ),
            "created_at": (existing.created_at if existing is not None else None) or now,
            "last_activity_at": last_activity_at or now,
            "lease_expires_at": lease_expires_at,
            "idle_timeout_s": _idle_timeout_s(),
            "updated_at": now,
        }
        row.sandbox_state = json.dumps(state)
        row.sandbox_session_id = handle.sandbox_id
        fresh_db.add(row)
        fresh_db.commit()

        # Mirror onto the caller's in-memory object too (it may live in a
        # different, request-scoped session/identity map) so code in the same
        # request that reads `conversation.sandbox_state`/`sandbox_session_id`
        # immediately after this call sees the up-to-date value.
        if conversation is not None and conversation is not row:
            try:
                conversation.sandbox_state = row.sandbox_state
                conversation.sandbox_session_id = row.sandbox_session_id
            except Exception:
                pass
    except Exception as exc:
        logger.debug(
            "SandboxSessionService: cannot persist sandbox state (conversation_id=%s): %s",
            conversation_id,
            exc,
            exc_info=True,
        )
    finally:
        try:
            fresh_db.close()
        except Exception:
            pass


def _clear_persisted_sandbox_state(
    conversation: "Conversation | None",
    session_key: str | None,
) -> None:
    """Clear ``sandbox_session_id``/``sandbox_state``, in-memory and in the DB.

    Mirrors the thread-safety rationale in :func:`_persist_sandbox_state`:
    never writes through a caller-supplied session — always opens its own
    short-lived one.
    """
    if conversation is not None:
        try:
            conversation.sandbox_session_id = None
            conversation.sandbox_state = None
        except Exception:
            pass

    conversation_id = _resolve_conversation_id(conversation, session_key)
    if conversation_id is None:
        return

    try:
        from db.database import SessionLocal  # type: ignore[import]
        fresh_db = SessionLocal()
    except Exception as exc:
        logger.debug(
            "SandboxSessionService: cannot open DB session to clear sandbox state "
            "(conversation_id=%s): %s",
            conversation_id,
            exc,
            exc_info=True,
        )
        return

    try:
        from models.conversation import Conversation  # type: ignore[import]
        row = (
            fresh_db.query(Conversation)
            .filter(Conversation.conversation_id == conversation_id)
            .first()
        )
        if row is None:
            return
        row.sandbox_session_id = None
        row.sandbox_state = None
        fresh_db.add(row)
        fresh_db.commit()
    except Exception as exc:
        logger.warning(
            "SandboxSessionService: cannot clear persisted sandbox state (conversation_id=%s): %s",
            conversation_id,
            exc,
            exc_info=True,
        )
    finally:
        try:
            fresh_db.close()
        except Exception:
            pass


def _get_provider_by_name(name: str) -> SandboxProvider | None:
    """Return a zero-credential provider instance by its ``PROVIDER_NAME``.

    Only env-var defaults apply — no per-tenant credentials. Returns None if
    unknown. Prefer :func:`_provider_from_saved_state` when a
    ``SavedSandboxState`` (with a possible ``sandbox_service_id``) is
    available, so tenant-specific credentials are used instead.
    """
    try:
        from tools.sandbox.factory import _PROVIDER_REGISTRY  # type: ignore[import]
        cls = _PROVIDER_REGISTRY.get(name)
        return cls() if cls is not None else None
    except Exception:
        return None


def _provider_from_saved_state(state: SavedSandboxState) -> SandboxProvider | None:
    """Build a provider for a persisted sandbox state, using tenant credentials when known.

    If ``state.sandbox_service_id`` is set, resolves the ``SandboxService``
    row and builds the provider with that tenant's credentials (endpoint,
    api key, provider-specific extra config) — matching how the sandbox was
    originally created via ``tools.sandbox.factory.resolve_provider``. This
    ensures cleanup/reaper destroy calls target the same account/endpoint the
    sandbox actually lives on.

    Falls back to a zero-credential provider instance (env-var defaults only,
    via :func:`_get_provider_by_name`) when no ``sandbox_service_id`` is
    recorded (older persisted state written before this field existed) or the
    service lookup fails for any reason — a warning is logged in that
    fallback case so credential-mismatch destroy failures are visible in
    logs.
    """
    if state.sandbox_service_id is not None:
        try:
            from db.database import SessionLocal  # type: ignore[import]
            from repositories.sandbox_service_repository import (  # type: ignore[import]
                SandboxServiceRepository,
            )
            from tools.sandbox.factory import (  # type: ignore[import]
                _PROVIDER_REGISTRY,
                _credentials_from_service,
            )

            service_db = SessionLocal()
            try:
                service = SandboxServiceRepository.get_by_id(service_db, state.sandbox_service_id)
            finally:
                try:
                    service_db.close()
                except Exception:
                    pass

            if service is not None:
                provider_name = (service.provider or "").strip().lower()
                provider_cls = _PROVIDER_REGISTRY.get(provider_name)
                if provider_cls is not None:
                    return provider_cls(credentials=_credentials_from_service(service))
                logger.warning(
                    "SandboxSessionService: sandbox_service_id=%s references unregistered "
                    "provider '%s'; falling back to zero-credential provider '%s' to destroy "
                    "sandbox %s",
                    state.sandbox_service_id,
                    provider_name,
                    state.provider,
                    state.sandbox_id,
                )
            else:
                logger.warning(
                    "SandboxSessionService: sandbox_service_id=%s not found; falling back to "
                    "zero-credential provider '%s' to destroy sandbox %s — this destroy may "
                    "target the wrong account/endpoint",
                    state.sandbox_service_id,
                    state.provider,
                    state.sandbox_id,
                )
        except Exception as exc:
            logger.warning(
                "SandboxSessionService: error resolving tenant credentials for "
                "sandbox_service_id=%s; falling back to zero-credential provider '%s': %s",
                state.sandbox_service_id,
                state.provider,
                exc,
                exc_info=True,
            )
    else:
        logger.debug(
            "SandboxSessionService: no sandbox_service_id recorded for sandbox %s "
            "(provider=%s); using zero-credential provider for destroy — this may fail "
            "for tenants with custom credentials",
            state.sandbox_id,
            state.provider,
        )
    return _get_provider_by_name(state.provider)


def _destroy_persisted_sandbox(state: SavedSandboxState | None) -> bool:
    """Best-effort remote destroy for a persisted sandbox state snapshot.

    Returns:
        ``True`` when there was nothing to destroy, the destroy call
        succeeded, or the sandbox id/provider is missing (already-logged
        no-ops). ``False`` when a provider could not be resolved or the
        destroy call itself raised. Callers should only clear the
        DB-persisted state after a ``True`` result, so a failed destroy
        leaves behind the only record needed to retry later instead of
        silently orphaning the remote sandbox.
    """
    if state is None or not state.provider or not state.sandbox_id:
        return True
    provider = _provider_from_saved_state(state)
    if provider is None:
        logger.warning(
            "SandboxSessionService: cannot destroy persisted sandbox %s; "
            "unknown provider %s",
            state.sandbox_id,
            state.provider,
        )
        return False
    try:
        provider.destroy_sandbox_id(state.sandbox_id)
        return True
    except Exception as exc:
        logger.warning(
            "SandboxSessionService: error destroying persisted sandbox "
            "(provider=%s, sandbox_id=%s): %s",
            state.provider,
            state.sandbox_id,
            exc,
            exc_info=True,
        )
        return False


@dataclass
class _Entry:
    handle: SandboxHandle
    provider: SandboxProvider
    last_used: float = field(default_factory=time.monotonic)
    active_uses: int = 0
    created_at: float = field(default_factory=time.monotonic)
    lease_expires_at: float | None = None


class SandboxSessionService:
    """In-process registry of active sandbox handles, keyed by session_key."""

    _lock: threading.Lock
    _sessions: Dict[str, _Entry]
    _creation_locks: Dict[str, threading.Lock]
    _pending_creates: set

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: Dict[str, _Entry] = {}
        # Per-key locks serializing sandbox *creation* (not reuse/touch) so
        # two concurrent get_or_create() calls for the same session_key
        # cannot both create a sandbox. Guarded by self._lock (classic
        # double-checked locking for the lock dict itself).
        self._creation_locks: Dict[str, threading.Lock] = {}
        # Session keys with a reservation against the concurrency cap while
        # their (slow) sandbox creation is in flight, for DIFFERENT keys
        # racing concurrently — self._creation_locks only serializes the
        # SAME key. The cap check below must count these alongside
        # self._sessions so N concurrently-arriving new keys can't all
        # observe room under the cap and collectively overshoot it.
        self._pending_creates: set = set()
        self._reaper = threading.Thread(
            target=self._reaper_loop, daemon=True, name="sandbox-reaper"
        )
        self._reaper.start()

    # ------------------------------------------------------------------
    # Session key helper (Phase 2, step 2.3)
    # ------------------------------------------------------------------

    @staticmethod
    def session_key(
        agent_id: int,
        conversation_id: int | str | None,
        session_id: str | None = None,
    ) -> str:
        """Return a canonical sandbox session key.

        Priority:
        1. If *conversation_id* is given → ``"conv_{agent_id}_{conversation_id}"``
        2. If *session_id* is given       → ``"thread_{agent_id}_{session_id}"``
        3. Otherwise                       → ``"anon_{agent_id}"``
        """
        if conversation_id is not None:
            return f"conv_{agent_id}_{conversation_id}"
        if session_id is not None:
            return f"thread_{agent_id}_{session_id}"
        return f"anon_{agent_id}"

    # ------------------------------------------------------------------
    # Core lifecycle
    # ------------------------------------------------------------------

    def _get_creation_lock(self, session_key: str) -> threading.Lock:
        """Return (creating if needed) the per-key lock serializing creation."""
        with self._lock:
            lock = self._creation_locks.get(session_key)
            if lock is None:
                lock = threading.Lock()
                self._creation_locks[session_key] = lock
            return lock

    def get_or_create(
        self,
        session_key: str,
        provider: SandboxProvider,
        working_dir: str,
        *,
        conversation: "Conversation | None" = None,
        db: Session | None = None,
        sandbox_service_id: int | None = None,
    ) -> SandboxHandle:
        """Return an existing sandbox handle or create one.

        Cache-hit path: renew the sandbox TTL and return the existing handle.
        Cache-miss path: serialize creation per ``session_key`` (so concurrent
        callers cannot double-create), enforce the global concurrency cap,
        load state from DB (if available), create a new sandbox (passing
        ``existing_sandbox_id`` so the provider can attempt a resume), persist
        state to DB, and cache the handle.

        Args:
            session_key:        Canonical key, typically from ``session_key()``.
            provider:            Resolved ``SandboxProvider`` instance.
            working_dir:         Filesystem path the provider may use.
            conversation:        ORM ``Conversation`` object for DB persistence.
            db:                  Unused; retained for call-site compatibility
                                 (see :func:`_persist_sandbox_state`).
            sandbox_service_id: The resolved ``SandboxService.service_id`` that
                                 produced *provider*'s credentials, if any.
                                 Persisted so cleanup paths can rebuild a
                                 credential-bearing provider later.

        Returns:
            A live ``SandboxHandle``.

        Raises:
            SandboxCapacityError: If the global concurrent-session cap
                (``SANDBOX_MAX_CONCURRENT_SESSIONS``) has been reached and a
                new sandbox would need to be created.
        """
        with self._lock:
            entry = self._sessions.get(session_key)
            if entry is not None:
                try:
                    provider.touch_sandbox(entry.handle, _idle_timeout_s())
                    entry.last_used = time.monotonic()
                    entry.lease_expires_at = None
                    _persist_sandbox_state(
                        conversation, entry.handle, db=db, sandbox_service_id=sandbox_service_id
                    )
                    logger.debug(
                        "SandboxSessionService: reusing handle for %s (sandbox_id=%s)",
                        session_key,
                        entry.handle.sandbox_id,
                    )
                    return entry.handle
                except SandboxExpiredError:
                    self._sessions.pop(session_key, None)
                    logger.info(
                        "SandboxSessionService: cached sandbox expired for %s — recreating",
                        session_key,
                    )

        # Serialize *creation* per session_key: two concurrent callers for the
        # same key (double-submit, retry, request race) must not both create
        # a sandbox — the loser would otherwise be orphaned (never cached,
        # never destroyed, but still billable on remote providers).
        creation_lock = self._get_creation_lock(session_key)
        with creation_lock:
            # Double-check: another thread may have finished creating this
            # key's sandbox while we were waiting for the creation lock.
            with self._lock:
                entry = self._sessions.get(session_key)
            if entry is not None:
                try:
                    provider.touch_sandbox(entry.handle, _idle_timeout_s())
                    with self._lock:
                        entry.last_used = time.monotonic()
                        entry.lease_expires_at = None
                    _persist_sandbox_state(
                        conversation, entry.handle, db=db, sandbox_service_id=sandbox_service_id
                    )
                    logger.debug(
                        "SandboxSessionService: reusing handle created by a concurrent "
                        "caller for %s (sandbox_id=%s)",
                        session_key,
                        entry.handle.sandbox_id,
                    )
                    return entry.handle
                except SandboxExpiredError:
                    with self._lock:
                        self._sessions.pop(session_key, None)
                    logger.info(
                        "SandboxSessionService: concurrently-created sandbox expired for "
                        "%s — recreating",
                        session_key,
                    )

            # Global concurrency cap (process-wide, not per-app/tenant — a
            # per-app quota would require threading app_id through the
            # session key, which is out of scope here). Protects a shared
            # sandbox host (e.g. one OpenSandbox server) from being
            # exhausted by a single tenant opening many concurrent chats.
            #
            # The check-and-reserve below happens in ONE critical section so
            # that N concurrently-arriving DIFFERENT session_keys cannot each
            # observe room under the cap and all proceed — self._pending_creates
            # accounts for in-flight creations (which can take up to
            # SANDBOX_CREATE_TIMEOUT_S) alongside already-live self._sessions.
            # self._creation_locks above only serializes the SAME key.
            max_sessions = _max_concurrent_sessions()
            with self._lock:
                live_count = len(self._sessions) + len(self._pending_creates)
                if live_count >= max_sessions:
                    logger.warning(
                        "SandboxSessionService: refusing to create sandbox for %s — "
                        "concurrent session cap reached (%s/%s)",
                        session_key,
                        live_count,
                        max_sessions,
                    )
                    raise SandboxCapacityError(
                        f"Maximum concurrent sandbox sessions ({max_sessions}) reached. "
                        "Try again once an existing sandbox session becomes idle."
                    )
                self._pending_creates.add(session_key)

            try:
                saved_state = _load_sandbox_state(conversation)
                if _state_is_idle_expired(saved_state):
                    logger.info(
                        "SandboxSessionService: persisted sandbox for %s expired by idle "
                        "timeout; destroying and creating fresh",
                        session_key,
                    )
                    destroyed = _destroy_persisted_sandbox(saved_state)
                    if destroyed:
                        _clear_persisted_sandbox_state(conversation, session_key)
                    else:
                        logger.warning(
                            "SandboxSessionService: could not confirm destroy of idle-expired "
                            "sandbox for %s; leaving persisted DB state for a future retry "
                            "(it will be overwritten once the fresh sandbox below is created)",
                            session_key,
                        )
                    saved_state = None
                logger.info(
                    "SandboxSessionService: creating sandbox for %s (provider=%s, timeout_s=%s)",
                    session_key,
                    provider.PROVIDER_NAME,
                    _create_timeout_s(),
                )
                try:
                    handle = self._create_sandbox_with_timeout(
                        provider,
                        working_dir,
                        session_key=session_key,
                        existing_sandbox_id=saved_state.sandbox_id if saved_state else None,
                    )
                except SandboxExpiredError:
                    if saved_state is None:
                        raise
                    logger.info(
                        "SandboxSessionService: persisted sandbox for %s was unavailable "
                        "during resume; creating fresh",
                        session_key,
                    )
                    # The provider itself reports the sandbox is gone (unlike the
                    # idle-expiry branch above, there is nothing to destroy) —
                    # clearing is always appropriate here, matching evict()'s
                    # semantics for a confirmed-gone remote sandbox.
                    saved_state = None
                    _clear_persisted_sandbox_state(conversation, session_key)
                    handle = self._create_sandbox_with_timeout(
                        provider,
                        working_dir,
                        session_key=session_key,
                        existing_sandbox_id=None,
                    )

                _persist_sandbox_state(
                    conversation, handle, db=db, sandbox_service_id=sandbox_service_id
                )

                with self._lock:
                    self._sessions[session_key] = _Entry(handle=handle, provider=provider)

                logger.info(
                    "SandboxSessionService: created sandbox for %s (sandbox_id=%s, provider=%s)",
                    session_key,
                    handle.sandbox_id,
                    handle.provider_name,
                )
                return handle
            finally:
                # Release the reservation whether creation succeeded (now
                # counted via self._sessions instead) or failed (freed up).
                with self._lock:
                    self._pending_creates.discard(session_key)

    def _create_sandbox_with_timeout(
        self,
        provider: SandboxProvider,
        working_dir: str,
        *,
        session_key: str | None = None,
        existing_sandbox_id: str | None = None,
    ) -> SandboxHandle:
        timeout_s = _create_timeout_s()
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sandbox_create")
        future = executor.submit(
            provider.create_sandbox,
            working_dir=working_dir,
            session_key=session_key,
            existing_sandbox_id=existing_sandbox_id,
        )
        try:
            return future.result(timeout=timeout_s)
        except TimeoutError as exc:
            future.cancel()
            logger.error(
                "SandboxSessionService: sandbox creation timed out after %ss (provider=%s)",
                timeout_s,
                provider.PROVIDER_NAME,
            )
            raise RuntimeError(
                f"Sandbox provider '{provider.PROVIDER_NAME}' did not create a sandbox "
                f"within {timeout_s}s. Check the OpenSandbox server, Docker socket, "
                "and sandbox image availability."
            ) from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def evict(self, session_key: str) -> None:
        """Remove the cached entry for *session_key* WITHOUT calling destroy_sandbox.

        Use this after a :class:`~tools.sandbox.provider.SandboxExpiredError` is
        caught — the container is already gone so there is nothing to kill.  The
        next call to :meth:`get_or_create` will then create a fresh sandbox.

        Safe to call when no entry exists for the key.
        """
        with self._lock:
            entry = self._sessions.pop(session_key, None)

        if entry is not None:
            logger.info(
                "SandboxSessionService.evict: removed stale cache entry for %s "
                "(sandbox_id=%s)",
                session_key,
                entry.handle.sandbox_id,
            )

    def begin_use(
        self,
        session_key: str,
        *,
        conversation: "Conversation | None" = None,
        db: Session | None = None,
        expected_seconds: int | None = None,
        sandbox_service_id: int | None = None,
    ) -> bool:
        """Mark a sandbox session as actively executing work.

        The idle reaper skips entries with active uses so long-running code
        execution cannot be mistaken for an idle sandbox. Returns ``True`` when
        the session exists and was marked.
        """
        ttl_s = _idle_timeout_s()
        now_mono = time.monotonic()
        lease_seconds = max(ttl_s, int(expected_seconds or 0) + ttl_s)
        lease_expires_mono = now_mono + lease_seconds
        lease_expires_at = (_utc_now() + timedelta(seconds=lease_seconds)).isoformat() + "Z"
        with self._lock:
            entry = self._sessions.get(session_key)
            if entry is None:
                return False
            entry.active_uses += 1
            entry.last_used = now_mono
            entry.lease_expires_at = lease_expires_mono
            handle = entry.handle
            provider = entry.provider
        try:
            provider.touch_sandbox(handle, lease_seconds)
        except SandboxExpiredError:
            self.evict(session_key)
            raise
        except Exception as exc:
            logger.debug(
                "SandboxSessionService.begin_use: provider touch failed (key=%s): %s",
                session_key,
                exc,
                exc_info=True,
            )
        _persist_sandbox_state(
            conversation,
            handle,
            db=db,
            lease_expires_at=lease_expires_at,
            sandbox_service_id=sandbox_service_id,
        )
        return True

    def end_use(
        self,
        session_key: str,
        *,
        conversation: "Conversation | None" = None,
        db: Session | None = None,
        sandbox_service_id: int | None = None,
    ) -> None:
        """Clear one active-use marker and refresh the idle timestamp."""
        handle = None
        provider = None
        with self._lock:
            entry = self._sessions.get(session_key)
            if entry is None:
                return
            entry.active_uses = max(0, entry.active_uses - 1)
            entry.last_used = time.monotonic()
            if entry.active_uses == 0:
                entry.lease_expires_at = None
            handle = entry.handle
            provider = entry.provider
        try:
            provider.touch_sandbox(handle, _idle_timeout_s())
        except SandboxExpiredError:
            self.evict(session_key)
            raise
        except Exception as exc:
            logger.debug(
                "SandboxSessionService.end_use: provider touch failed (key=%s): %s",
                session_key,
                exc,
                exc_info=True,
            )
        _persist_sandbox_state(conversation, handle, db=db, sandbox_service_id=sandbox_service_id)

    @contextmanager
    def use(
        self,
        session_key: str,
        *,
        conversation: "Conversation | None" = None,
        db: Session | None = None,
        expected_seconds: int | None = None,
        sandbox_service_id: int | None = None,
    ):
        """Context manager that protects a sandbox from idle reaping while used."""
        acquired = self.begin_use(
            session_key,
            conversation=conversation,
            db=db,
            expected_seconds=expected_seconds,
            sandbox_service_id=sandbox_service_id,
        )
        try:
            yield acquired
        finally:
            if acquired:
                self.end_use(
                    session_key,
                    conversation=conversation,
                    db=db,
                    sandbox_service_id=sandbox_service_id,
                )

    def record_activity(
        self,
        session_key: str,
        *,
        conversation: "Conversation | None" = None,
        db: Session | None = None,
        sandbox_service_id: int | None = None,
    ) -> None:
        """Persist a completed non-REPL sandbox activity as last-use."""
        with self._lock:
            entry = self._sessions.get(session_key)
            if entry is None:
                return
            entry.last_used = time.monotonic()
            handle = entry.handle
        _persist_sandbox_state(conversation, handle, db=db, sandbox_service_id=sandbox_service_id)

    def destroy(self, session_key: str) -> None:
        """Destroy the sandbox associated with *session_key* and remove it.

        Safe to call even when no sandbox exists for the key.
        """
        with self._lock:
            entry = self._sessions.pop(session_key, None)

        if entry is None:
            return

        try:
            entry.provider.destroy_sandbox(entry.handle)
            logger.info(
                "SandboxSessionService: destroyed sandbox for %s (sandbox_id=%s)",
                session_key,
                entry.handle.sandbox_id,
            )
        except Exception as exc:
            logger.warning(
                "SandboxSessionService: error destroying sandbox for %s: %s",
                session_key,
                exc,
                exc_info=True,
            )

    def destroy_all_for_agent(self, agent_id: int) -> None:
        """Destroy all sandboxes that belong to *agent_id*.

        Called when an agent is deleted.  Matches all key patterns:
        ``conv_{agent_id}_*``, ``thread_{agent_id}_*``, and ``anon_{agent_id}``.
        """
        prefixes = (f"conv_{agent_id}_", f"thread_{agent_id}_", f"anon_{agent_id}")
        with self._lock:
            matching = [k for k in self._sessions if any(k.startswith(p) for p in prefixes)]
            entries = {k: self._sessions.pop(k) for k in matching}

        for key, entry in entries.items():
            try:
                entry.provider.destroy_sandbox(entry.handle)
                logger.info(
                    "SandboxSessionService: destroyed sandbox for agent deletion (key=%s)", key
                )
            except Exception as exc:
                logger.warning(
                    "SandboxSessionService: error destroying sandbox (key=%s): %s",
                    key,
                    exc,
                    exc_info=True,
                )

    # ------------------------------------------------------------------
    # Backend-restart handling (Q5)
    # ------------------------------------------------------------------

    def has_session(self, session_key: str) -> bool:
        """Return True if there is an in-memory handle for *session_key*."""
        with self._lock:
            return session_key in self._sessions

    def mark_session_lost(self, session_key: str) -> None:
        """Remove the stale entry without calling destroy on the provider.

        Called when a backend restart has already destroyed the underlying
        sandbox.  The caller is expected to surface a "sandbox state reset"
        message to the user.
        """
        with self._lock:
            self._sessions.pop(session_key, None)
        logger.info(
            "SandboxSessionService: marked session as lost (key=%s) — sandbox state reset",
            session_key,
        )

    # ------------------------------------------------------------------
    # Idle-TTL reaper (background daemon thread)
    # ------------------------------------------------------------------

    def _reaper_loop(self) -> None:
        """Daemon loop: periodically reap sandboxes idle longer than the TTL."""
        while True:
            time.sleep(_reap_interval_s())
            db = None
            try:
                try:
                    from db.database import SessionLocal  # type: ignore[import]
                    db = SessionLocal()
                except Exception:
                    db = None
                self._reap_stale(db=db)
            except Exception as exc:
                logger.warning("SandboxSessionService: reaper error: %s", exc, exc_info=True)
            finally:
                if db is not None:
                    try:
                        db.close()
                    except Exception:
                        pass

    def _reap_stale(self, *, db: Session | None = None) -> None:
        """Destroy sandbox sessions idle for longer than SANDBOX_IDLE_TIMEOUT_S.

        When *db* is provided, also clears DB-persisted sandbox state for stale
        conversations (useful after server restarts when the in-memory cache is empty).
        """
        ttl_s = _idle_timeout_s()

        # --- Reap in-memory stale entries ---
        now = time.monotonic()
        with self._lock:
            stale_keys = [
                k for k, e in self._sessions.items()
                if (
                    e.active_uses <= 0
                    and (e.lease_expires_at is None or e.lease_expires_at < now)
                    and (now - e.last_used) > ttl_s
                )
            ]
            stale_entries = {k: self._sessions.pop(k) for k in stale_keys}

        for key, entry in stale_entries.items():
            idle_s = now - entry.last_used
            try:
                entry.provider.destroy_sandbox(entry.handle)
                logger.info(
                    "SandboxSessionService: reaped idle sandbox (key=%s, idle=%.0fs, sandbox_id=%s)",
                    key, idle_s, entry.handle.sandbox_id,
                )
            except Exception as exc:
                logger.warning(
                    "SandboxSessionService: error reaping sandbox (key=%s): %s",
                    key, exc, exc_info=True,
                )

        # --- Opportunistic cleanup of unused per-key creation locks ---
        # Bounded, best-effort: only drop a lock when its key is no longer
        # live AND it is not currently held (so a thread mid-creation for a
        # freshly-evicted key is never disturbed).
        with self._lock:
            stale_lock_keys = [
                k for k, lock in self._creation_locks.items()
                if k not in self._sessions and not lock.locked()
            ]
            for k in stale_lock_keys:
                self._creation_locks.pop(k, None)

        # --- NEW: reap DB-persisted stale sandbox state ---
        if db is None:
            return

        try:
            from models.conversation import Conversation  # type: ignore[import]
        except Exception:
            return

        cutoff = _utc_now() - timedelta(seconds=ttl_s)
        try:
            stale_conversations = (
                db.query(Conversation)
                .filter(Conversation.sandbox_session_id.isnot(None))
                .all()
            )
        except Exception as exc:
            logger.warning("SandboxSessionService: DB reap query failed: %s", exc)
            return

        for conv in stale_conversations:
            state = _load_sandbox_state(conv)
            if state is None:
                # Orphaned sandbox_session_id with no state — just clear it
                # (there is no provider/sandbox_id information to act on).
                conv.sandbox_session_id = None
                conv.sandbox_state = None
                db.add(conv)
                continue
            with self._lock:
                if state.session_key in self._sessions:
                    # The in-memory registry owns active process-local sessions.
                    # Its monotonic clock/active-use lease is fresher than DB state.
                    continue
            activity_at = _state_activity_at(state) or datetime.min
            lease_expires_at = _parse_utc(state.lease_expires_at)
            if lease_expires_at is not None and lease_expires_at >= _utc_now():
                continue
            if activity_at < cutoff:
                # Best-effort remote destroy — only clear the DB record once
                # the destroy is confirmed, so a failure leaves behind the
                # only record needed to retry instead of orphaning the
                # remote sandbox permanently.
                if _destroy_persisted_sandbox(state):
                    conv.sandbox_session_id = None
                    conv.sandbox_state = None
                    db.add(conv)
                else:
                    logger.warning(
                        "SandboxSessionService: leaving persisted sandbox state intact "
                        "after failed destroy (key=%s, sandbox_id=%s)",
                        state.session_key,
                        state.sandbox_id,
                    )
        try:
            db.commit()
        except Exception as exc:
            logger.warning("SandboxSessionService: DB reap commit failed: %s", exc)


# Module-level singleton used across the application
sandbox_session_service = SandboxSessionService()
