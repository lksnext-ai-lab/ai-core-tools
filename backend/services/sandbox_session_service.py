"""
SandboxSessionService — manages SandboxHandle lifecycle per conversation.

A sandbox is keyed by ``session_key`` (typically the LangGraph thread_id,
i.e. ``f"thread_{agent_id}_{session_id}"``).  One active handle is kept
in memory per key; the underlying sandbox is created lazily on first use.

Open-question resolutions encoded here:

- Q2 (sandbox file scope): sandboxes are scoped to the conversation
  (session_key).  Cross-conversation persistence is deferred.
- Q5 (backend restart): the ``sandbox_session_id`` stored on
  ``Conversation`` records the provider's opaque sandbox ID.  When a
  conversation is resumed after a backend restart the sandbox is gone
  from memory; the service exposes ``mark_session_lost`` so callers can
  surface a "sandbox state reset" message to the user.
"""

from __future__ import annotations

import threading
import time
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass, field
from typing import Dict, Optional

from utils.logger import get_logger
from tools.sandbox.provider import SandboxProvider, SandboxHandle

logger = get_logger(__name__)

_DEFAULT_CREATE_TIMEOUT_S = 60


def _create_timeout_s() -> int:
    try:
        return int(os.getenv("SANDBOX_CREATE_TIMEOUT_S", str(_DEFAULT_CREATE_TIMEOUT_S)))
    except (TypeError, ValueError):
        return _DEFAULT_CREATE_TIMEOUT_S


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
    # Core lifecycle
    # ------------------------------------------------------------------

    def get_or_create(
        self,
        session_key: str,
        provider: SandboxProvider,
        working_dir: str,
    ) -> SandboxHandle:
        """Return an existing sandbox handle or create one.

        Args:
            session_key:  Unique key for the conversation, e.g.
                          ``"thread_{agent_id}_{session_id}"``.
            provider:     Resolved ``SandboxProvider`` instance.
            working_dir:  Filesystem path the provider may use.

        Returns:
            A live ``SandboxHandle``.
        """
        with self._lock:
            entry = self._sessions.get(session_key)
            if entry is not None:
                entry.last_used = time.monotonic()
                logger.debug(
                    "SandboxSessionService: reusing handle for %s (sandbox_id=%s)",
                    session_key,
                    entry.handle.sandbox_id,
                )
                return entry.handle

            logger.info(
                "SandboxSessionService: creating sandbox for %s (provider=%s, timeout_s=%s)",
                session_key,
                provider.PROVIDER_NAME,
                _create_timeout_s(),
            )
            handle = self._create_sandbox_with_timeout(provider, working_dir)
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
    ) -> SandboxHandle:
        timeout_s = _create_timeout_s()
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sandbox_create")
        future = executor.submit(provider.create_sandbox, working_dir=working_dir)
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

        Called when an agent is deleted, so no orphaned sandboxes leak.
        Session keys follow the pattern ``"thread_{agent_id}_{session_id}"``.
        """
        prefix = f"thread_{agent_id}_"
        with self._lock:
            matching = [k for k in self._sessions if k.startswith(prefix)]
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

    def _reap_stale(self) -> None:
        """Destroy sandbox sessions that have been idle for longer than SANDBOX_SESSION_TTL_H."""
        try:
            ttl_s = int(os.getenv("SANDBOX_SESSION_TTL_H", "2")) * 3600
        except (TypeError, ValueError):
            ttl_s = 2 * 3600

        now = time.monotonic()
        with self._lock:
            stale_keys = [
                k for k, e in self._sessions.items()
                if (now - e.last_used) > ttl_s
            ]
            stale_entries = {k: self._sessions.pop(k) for k in stale_keys}

        if not stale_entries:
            return

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


# Module-level singleton used across the application
sandbox_session_service = SandboxSessionService()
