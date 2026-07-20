"""
SandboxProvider abstract base class and SandboxHandle dataclass.

Every concrete provider (opensandbox, daytona, e2b, …) must subclass
SandboxProvider and implement all abstract methods.

v2 changes (sandbox-v2-migration Phase 1):
- ``SandboxHandle`` extended with ``session_key``.
- ``SandboxExpiredError`` added for explicit expiry signalling.
- Provider ABC updated: ``create_sandbox`` accepts ``existing_sandbox_id``;
  ``renew_sandbox`` added (default no-op); ``run_code`` gains ``timeout``,
  ``max_output_chars``, and ``on_stderr``; ``run_code_streaming`` helper added.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any


class SandboxExpiredError(RuntimeError):
    """Raised when a provider sandbox no longer exists and cannot be recovered.

    Callers that catch this error should evict the cached handle and call
    ``create_sandbox`` again.
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
                       Not for application use.
    """

    sandbox_id: str
    working_dir: str
    provider_name: str
    session_key: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


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

    requires_file_sync: bool = True
    """Whether this provider's sandbox filesystem is remote/separate from the
    backend's local ``working_dir`` and therefore needs explicit file push/pull
    to stay in sync.

    Declared as a class attribute so a future provider must consciously set
    it (rather than any caller string-matching on provider names). Defaults
    to ``True`` since every provider that manages a remote sandbox execution
    environment needs file synchronisation; a provider whose sandbox shares
    the backend's local filesystem directly would set this to ``False``.
    """

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

        Default implementation is a no-op; providers without TTL support may
        leave this unimplemented.  Providers with TTL support (e.g.
        ``OpenSandboxProvider``) should override this and raise
        :exc:`SandboxExpiredError` if the remote sandbox is gone.
        """

    def touch_sandbox(self, handle: SandboxHandle, idle_timeout_s: int) -> None:
        """Record provider-side activity and refresh the idle timeout.

        The session service owns idle detection. Providers use this hook to keep
        their own timeout/auto-stop setting aligned with that service-level
        activity. The default bridges to the older ``renew_sandbox`` hook.
        """
        self.renew_sandbox(handle, timedelta(seconds=idle_timeout_s))

    @abstractmethod
    def destroy_sandbox(self, handle: SandboxHandle) -> None:
        """Release all resources held by the sandbox."""

    def destroy_sandbox_id(self, sandbox_id: str) -> None:
        """Best-effort destroy by provider sandbox id.

        Used by persisted-state cleanup after backend restarts, when the live
        SDK object stored in ``SandboxHandle.metadata`` is no longer available.
        Providers with remote resume/connect APIs should override this method.
        """
        self.destroy_sandbox(
            SandboxHandle(
                sandbox_id=sandbox_id,
                working_dir="",
                provider_name=getattr(self, "PROVIDER_NAME", self.__class__.__name__),
            )
        )

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

        Paths are relative to the sandbox working directory.
        """
