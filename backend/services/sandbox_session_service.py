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
"""

from __future__ import annotations

import json
import threading
import time
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

from sqlalchemy.orm import Session

from utils.logger import get_logger
from tools.sandbox.provider import SandboxProvider, SandboxHandle, SandboxExpiredError

if TYPE_CHECKING:
    from models.conversation import Conversation

logger = get_logger(__name__)

_DEFAULT_CREATE_TIMEOUT_S = 60


def _create_timeout_s() -> int:
    try:
        return int(os.getenv("SANDBOX_CREATE_TIMEOUT_S", str(_DEFAULT_CREATE_TIMEOUT_S)))
    except (TypeError, ValueError):
        return _DEFAULT_CREATE_TIMEOUT_S


def _renew_duration() -> timedelta:
    try:
        import config as settings  # type: ignore[import]
        return timedelta(minutes=settings.SANDBOX_RENEW_MINUTES)
    except Exception:
        return timedelta(minutes=30)


# ---------------------------------------------------------------------------
# DB state helpers (Phase 2)
# ---------------------------------------------------------------------------

@dataclass
class SavedSandboxState:
    """Deserialized snapshot of ``Conversation.sandbox_state``."""
    provider: str
    session_key: str
    sandbox_id: str
    active_skills: dict[str, dict[str, Any]]
    updated_at: str


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
            active_skills=data.get("active_skills", {}),
            updated_at=data.get("updated_at", ""),
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def _persist_sandbox_state(
    conversation: "Conversation | None",
    handle: SandboxHandle,
    *,
    db: Session | None,
) -> None:
    """Serialize SandboxHandle state into ``Conversation.sandbox_state`` and commit."""
    if conversation is None or db is None:
        return
    state = {
        "provider": handle.provider_name,
        "session_key": handle.session_key,
        "sandbox_id": handle.sandbox_id,
        "active_skills": handle.active_skills,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    conversation.sandbox_state = json.dumps(state)
    conversation.sandbox_session_id = handle.sandbox_id
    db.add(conversation)
    db.commit()


def _get_provider_by_name(name: str) -> SandboxProvider | None:
    """Return a provider instance by its ``PROVIDER_NAME``.  Returns None if unknown."""
    try:
        from tools.sandbox.factory import _PROVIDER_REGISTRY  # type: ignore[import]
        cls = _PROVIDER_REGISTRY.get(name)
        return cls() if cls is not None else None
    except Exception:
        return None


@dataclass
class _Entry:
    handle: SandboxHandle
    provider: SandboxProvider
    active_skills: list = field(default_factory=list)
    last_used: float = field(default_factory=time.monotonic)


class SandboxSessionService:
    """In-process registry of active sandbox handles, keyed by session_key."""

    _lock: threading.Lock
    _sessions: Dict[str, _Entry]

    _REAP_INTERVAL_S = 600  # check for stale sessions every 10 minutes

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: Dict[str, _Entry] = {}
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

    def get_or_create(
        self,
        session_key: str,
        provider: SandboxProvider,
        working_dir: str,
        *,
        conversation: "Conversation | None" = None,
        db: Session | None = None,
        skills_loader: "Callable[[list[int]], list[Any]] | None" = None,
    ) -> SandboxHandle:
        """Return an existing sandbox handle or create one.

        Cache-hit path: renew the sandbox TTL and return the existing handle.
        Cache-miss path: load state from DB (if available), create a new sandbox
        (passing ``existing_sandbox_id`` so the provider can attempt a resume),
        persist state to DB, and cache the handle.

        When *skills_loader* is provided and the provider had to create a fresh
        sandbox (resume failed — new sandbox_id differs from saved one), the
        loader is called to re-activate all skills that were previously active.

        Args:
            session_key:    Canonical key, typically from ``session_key()``.
            provider:       Resolved ``SandboxProvider`` instance.
            working_dir:    Filesystem path the provider may use.
            conversation:   ORM ``Conversation`` object for DB persistence.
            db:             SQLAlchemy session.  Required for DB persistence.
            skills_loader:  Optional callable that accepts a list of skill IDs and
                            returns a list of :class:`~models.skill.Skill` ORM objects.
                            Called when a sandbox is re-created after expiry so that
                            previously-active skills are re-installed.

        Returns:
            A live ``SandboxHandle``.
        """
        with self._lock:
            entry = self._sessions.get(session_key)
            if entry is not None:
                try:
                    provider.renew_sandbox(entry.handle, _renew_duration())
                    entry.last_used = time.monotonic()
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

        saved_state = _load_sandbox_state(conversation)
        logger.info(
            "SandboxSessionService: creating sandbox for %s (provider=%s, timeout_s=%s)",
            session_key,
            provider.PROVIDER_NAME,
            _create_timeout_s(),
        )
        handle = self._create_sandbox_with_timeout(
            provider,
            working_dir,
            session_key=session_key,
            existing_sandbox_id=saved_state.sandbox_id if saved_state else None,
        )

        is_fresh_sandbox = saved_state and saved_state.sandbox_id != handle.sandbox_id
        if is_fresh_sandbox:
            handle.active_skills = {}
            # Phase 3: re-activate previously-active skills if a loader was provided.
            if skills_loader is not None and saved_state.active_skills:
                skill_ids = list(saved_state.active_skills.keys())
                try:
                    skills = skills_loader(skill_ids)
                    for skill in skills:
                        try:
                            provider.ensure_skill(handle, skill)
                        except Exception as exc:
                            logger.warning(
                                "SandboxSessionService: failed to re-activate skill '%s' "
                                "after sandbox recreation: %s",
                                skill.name,
                                exc,
                            )
                except Exception as exc:
                    logger.warning(
                        "SandboxSessionService: skills_loader raised during skill reload: %s",
                        exc,
                    )
        elif saved_state:
            handle.active_skills = dict(saved_state.active_skills)

        _persist_sandbox_state(conversation, handle, db=db)

        with self._lock:
            self._sessions[session_key] = _Entry(handle=handle, provider=provider)

        logger.info(
            "SandboxSessionService: created sandbox for %s (sandbox_id=%s, provider=%s)",
            session_key,
            handle.sandbox_id,
            handle.provider_name,
        )
        return handle

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
    # Skill activation (IT-3 hooks — stubs for now)
    # ------------------------------------------------------------------

    def ensure_skill(self, session_key: str, skill) -> None:
        """Activate a skill's runtime dependencies inside the sandbox.

        Implementation deferred to IT-3.
        """
        with self._lock:
            entry = self._sessions.get(session_key)
        if entry is None:
            raise RuntimeError(f"No active sandbox for session key '{session_key}'.")
        entry.provider.ensure_skill(entry.handle, skill)
        if skill.name not in entry.active_skills:
            entry.active_skills.append(skill.name)

    def list_active_skills(self, session_key: str) -> list[str]:
        """Return names of skills activated in the session's sandbox.

        Implementation deferred to IT-3.
        """
        with self._lock:
            entry = self._sessions.get(session_key)
        if entry is None:
            return []
        return list(entry.active_skills)

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
            time.sleep(self._REAP_INTERVAL_S)
            try:
                self._reap_stale()
            except Exception as exc:
                logger.warning("SandboxSessionService: reaper error: %s", exc, exc_info=True)

    def _reap_stale(self, *, db: Session | None = None) -> None:
        """Destroy sandbox sessions that have been idle for longer than SANDBOX_SESSION_TTL_H.

        When *db* is provided, also clears DB-persisted sandbox state for stale
        conversations (useful after server restarts when the in-memory cache is empty).
        """
        try:
            ttl_s = int(os.getenv("SANDBOX_SESSION_TTL_H", "2")) * 3600
        except (TypeError, ValueError):
            ttl_s = 2 * 3600

        # --- Reap in-memory stale entries ---
        now = time.monotonic()
        with self._lock:
            stale_keys = [
                k for k, e in self._sessions.items()
                if (now - e.last_used) > ttl_s
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

        # --- NEW: reap DB-persisted stale sandbox state ---
        if db is None:
            return

        try:
            from models.conversation import Conversation  # type: ignore[import]
        except Exception:
            return

        cutoff = datetime.utcnow() - timedelta(seconds=ttl_s)
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
                conv.sandbox_session_id = None
                conv.sandbox_state = None
                db.add(conv)
                continue
            try:
                updated_at = datetime.fromisoformat(state.updated_at.rstrip("Z"))
            except (ValueError, AttributeError):
                updated_at = datetime.min
            if updated_at < cutoff:
                # Best-effort remote destroy
                try:
                    provider = _get_provider_by_name(state.provider)
                    if provider:
                        handle = SandboxHandle(
                            sandbox_id=state.sandbox_id,
                            working_dir="",
                            provider_name=state.provider,
                            session_key=state.session_key,
                        )
                        provider.destroy_sandbox(handle)
                except Exception:
                    pass  # Best effort; clear DB state regardless
                conv.sandbox_session_id = None
                conv.sandbox_state = None
                db.add(conv)
        try:
            db.commit()
        except Exception as exc:
            logger.warning("SandboxSessionService: DB reap commit failed: %s", exc)


# Module-level singleton used across the application
sandbox_session_service = SandboxSessionService()
