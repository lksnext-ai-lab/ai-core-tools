"""
SandboxProvider abstract base class and SandboxHandle dataclass.

Every concrete provider (subprocess, opensandbox, …) must subclass
SandboxProvider and implement all abstract methods.

v2 changes (sandbox-v2-migration Phase 1):
- ``SandboxHandle`` extended with ``session_key`` and typed ``active_skills``.
- ``SandboxExpiredError`` added for explicit expiry signalling.
- Provider ABC updated: ``create_sandbox`` accepts ``existing_sandbox_id``;
  ``renew_sandbox`` added (default no-op); ``run_code`` gains ``timeout``,
  ``max_output_chars``, and ``on_stderr``; ``run_code_streaming`` helper added;
  ``ensure_skill`` / ``list_active_skills`` signatures tightened.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any


class SandboxExpiredError(RuntimeError):
    """Raised when a provider sandbox no longer exists and cannot be recovered.

    Callers that catch this error should evict the cached handle, call
    ``create_sandbox`` again (which will attempt resume if an
    ``existing_sandbox_id`` is available), and re-activate any Skills that
    were previously active.
    """


@dataclass
class SandboxHandle:
    """Opaque reference to a live sandbox session.

    Passed between the provider and the tool factory so neither side
    needs to know the other's internals.

    Attributes:
        sandbox_id:    Provider-assigned identifier for the remote sandbox.
        working_dir:   Host-side filesystem path used for local file staging.
        provider_name: Name of the provider that created this handle.
        session_key:   Derived session key used by ``SandboxSessionService``
                       (e.g. ``conv_12_456``).  Set after creation.
        metadata:      Provider-internal state (SDK objects, capability flags).
                       Not for application use — use ``active_skills`` instead.
        active_skills: Typed Skill activation state, keyed by skill name.
                       Each value is a dict with at minimum
                       ``{"sandbox_id": str, "phases": {"files": str, "bootstrap": str}}``.
    """

    sandbox_id: str
    working_dir: str
    provider_name: str
    session_key: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    # Typed Skill activation state for this concrete sandbox id.
    active_skills: dict[str, dict[str, Any]] = field(default_factory=dict)


class SandboxProvider(ABC):
    """Abstract base class for sandbox execution backends.

    Class attribute ``SUPPORTED_LANGUAGES`` declares which language identifiers
    this provider can execute.  Concrete providers override it as a class-level
    list; the default is ``["python"]`` for backward compatibility.

    Language identifiers are lowercase strings (e.g. ``"python"``,
    ``"javascript"``, ``"bash"``).  The set of recognised identifiers is
    intentionally open-ended — providers map them to the runtime primitives they
    support (subprocess interpreters, SDK enum values, etc.).
    """

    SUPPORTED_LANGUAGES: list[str] = ["python"]

    def get_supported_languages(self) -> list[str]:
        """Return the list of language identifiers this provider supports.

        Concrete providers that compute the list dynamically (e.g. by reading
        an environment variable) should override this method instead of the
        class attribute.
        """
        return list(self.SUPPORTED_LANGUAGES)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    def create_sandbox(
        self,
        working_dir: str,
        *,
        session_key: str | None = None,
        existing_sandbox_id: str | None = None,
    ) -> SandboxHandle:
        """Initialise or resume a sandbox and return a handle to it.

        Providers that support reconnecting should attempt to resume
        *existing_sandbox_id* when it is provided.  If resume fails, a new
        sandbox must be created.  Providers that do not support resume should
        ignore *existing_sandbox_id* and always create a new sandbox.

        Args:
            working_dir:         Host-side filesystem path for local staging.
            session_key:         Session key to store on the returned handle.
            existing_sandbox_id: Provider sandbox id to attempt resumption of.
        """

    def renew_sandbox(self, handle: SandboxHandle, duration: timedelta) -> None:
        """Extend the provider TTL by *duration*.

        Default implementation is a no-op; providers without TTL support (e.g.
        ``SubprocessProvider``) may leave this unimplemented.  Providers with
        TTL support (e.g. ``OpenSandboxProvider``) should override this and
        raise :exc:`SandboxExpiredError` if the remote sandbox is gone.
        """

    @abstractmethod
    def destroy_sandbox(self, handle: SandboxHandle) -> None:
        """Release all resources held by the sandbox."""

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    @abstractmethod
    def run_code(
        self,
        handle: SandboxHandle,
        code: str,
        *,
        language: str = "python",
        timeout: int | None = None,
        max_output_chars: int | None = None,
        on_stdout: Callable[[str], None] | None = None,
        on_stderr: Callable[[str], None] | None = None,
    ) -> str:
        """Execute *code* inside the sandbox and return truncated combined output.

        Args:
            handle:           Active sandbox handle.
            code:             Source code to execute.
            language:         Language identifier (e.g. ``"python"``).
                              Must be in :meth:`get_supported_languages`.
            timeout:          Per-execution timeout in seconds.  Falls back to
                              ``settings.SANDBOX_DEFAULT_TIMEOUT_S`` when ``None``.
            max_output_chars: Maximum characters to return.  Falls back to
                              ``settings.SANDBOX_MAX_OUTPUT_CHARS`` when ``None``.
                              Truncated output ends with a marker string.
            on_stdout:        Callback for live stdout lines (non-blocking).
            on_stderr:        Callback for live stderr lines (non-blocking).
        """

    def run_code_streaming(
        self,
        handle: SandboxHandle,
        code: str,
        stream_writer: Callable[[dict], None],
        **kwargs: Any,
    ) -> str:
        """Execute *code* and forward stdout/stderr to a LangGraph stream writer.

        Bridges the provider's ``on_stdout`` / ``on_stderr`` callbacks to
        ``stream_writer`` as ``{"type": "code_output", "stream": ..., "line": ...}``
        events.  Any keyword arguments are forwarded to :meth:`run_code`.

        Args:
            handle:        Active sandbox handle.
            code:          Source code to execute.
            stream_writer: Callable that accepts a dict and forwards it to the
                           LangGraph custom stream.
            **kwargs:      Extra arguments forwarded to :meth:`run_code`
                           (e.g. ``language``, ``timeout``).
        """

        def _stdout(line: str) -> None:
            try:
                stream_writer({"type": "code_output", "stream": "stdout", "line": line})
            except Exception:
                pass

        def _stderr(line: str) -> None:
            try:
                stream_writer({"type": "code_output", "stream": "stderr", "line": line})
            except Exception:
                pass

        return self.run_code(handle, code, on_stdout=_stdout, on_stderr=_stderr, **kwargs)

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    @abstractmethod
    def write_file(self, handle: SandboxHandle, filename: str, content: bytes) -> None:
        """Write *content* to *filename* inside the sandbox workspace."""

    @abstractmethod
    def read_file(self, handle: SandboxHandle, filename: str) -> bytes:
        """Return the raw bytes of *filename* from the sandbox workspace."""

    @abstractmethod
    def list_files(self, handle: SandboxHandle) -> list[str]:
        """Return workspace-relative paths of all files in the sandbox workspace.

        Paths are relative to the sandbox working directory.  The ``.skills/``
        directory and its contents are excluded from the result.
        """

    # ------------------------------------------------------------------
    # Skill activation
    # ------------------------------------------------------------------

    @abstractmethod
    def ensure_skill(
        self, handle: SandboxHandle, skill: Any, *, retry: bool = False
    ) -> dict[str, Any]:
        """Activate a Skill and return its phase status dict.

        The returned dict must contain at minimum::

            {
                "skill_id": int,
                "skill_name": str,
                "sandbox_id": str,
                "phases": {
                    "files": "ok" | "skipped" | "failed: <reason>",
                    "bootstrap": "ok" | "skipped" | "failed: <reason>",
                },
            }

        The result is stored in ``handle.active_skills[skill.name]`` by the
        provider and may also be persisted to ``Conversation.sandbox_state``
        by ``SandboxSessionService``.

        When *retry* is ``True``, the provider must re-run setup even if the
        Skill was previously recorded as active for this sandbox id.
        """

    @abstractmethod
    def list_active_skills(self, handle: SandboxHandle) -> dict[str, dict[str, Any]]:
        """Return the typed Skill activation state from ``handle.active_skills``."""
