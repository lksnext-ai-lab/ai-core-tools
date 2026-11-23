"""Per-turn guards that only the App Chat applies to the sandbox tools.

* ``redacted_logs`` / ``describe_exc``: on a Chat turn a provider exception text (it can echo code, file names or
  user data) never reaches the logs: only the exception class name does (same rule as
  ``utils.turn_failure_log``). Agents keep their current logging.
* ``ChatSandboxLimits``: one execution budget shared by the REPL tools and ``Bash``, a Bash timeout cap and no
  background shells (the provider offers no reliable way to kill them when the turn ends).

DB-free and import-light (used from ``tools.sandbox``).
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Iterator

import config as settings

_REDACTED: ContextVar[bool] = ContextVar("sandbox_redacted_logs", default=False)


@contextmanager
def redacted_logs(enabled: bool = True) -> Iterator[None]:
    """Within the block (and the threads/tasks copying this context) sandbox error logs carry class names only."""
    token = _REDACTED.set(bool(enabled) or _REDACTED.get())
    try:
        yield
    finally:
        _REDACTED.reset(token)


_PULL_GUARD: ContextVar = ContextVar("sandbox_pull_guard", default=None)


@contextmanager
def pull_guard(cancel: "threading.Event | None", deadline: float | None) -> Iterator[None]:
    """Within the block, bounded reads check ``cancel`` and a ``time.monotonic()`` deadline between chunks."""
    token = _PULL_GUARD.set((cancel, deadline))
    try:
        yield
    finally:
        _PULL_GUARD.reset(token)


def check_pull_guard() -> None:
    """Raise ``TimeoutError`` when the surrounding pull was cancelled or ran past its deadline."""
    import time

    guard = _PULL_GUARD.get()
    if guard is None:
        return
    cancel, deadline = guard
    if (cancel is not None and cancel.is_set()) or (deadline is not None and time.monotonic() > deadline):
        raise TimeoutError("sandbox pull cancelled or out of time")


def logs_are_redacted() -> bool:
    return _REDACTED.get()


def describe_exc(exc: BaseException) -> str:
    """``str(exc)`` normally, only the class name while logs are redacted."""
    return type(exc).__name__ if _REDACTED.get() else str(exc)


@dataclass
class ChatSandboxLimits:
    """Execution limits of ONE Chat turn (a fresh instance per ``create_agent`` call)."""

    max_executions: int = field(default_factory=lambda: int(getattr(settings, "SANDBOX_MAX_EXECUTIONS_PER_TURN", 5)))
    bash_max_timeout_s: int = field(default_factory=lambda: int(getattr(settings, "SANDBOX_CHAT_BASH_MAX_TIMEOUT_S", 60)))
    _count: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def consume(self) -> bool:
        """Count one code execution; False once the turn's budget is spent."""
        with self._lock:
            self._count += 1
            return self._count <= self.max_executions

    def cap_timeout(self, timeout_s: int) -> int:
        return max(1, min(int(timeout_s), self.bash_max_timeout_s))
