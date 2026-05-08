"""
SandboxProvider abstract base class and SandboxHandle dataclass.

Every concrete provider (subprocess, opensandbox, …) must subclass
SandboxProvider and implement all abstract methods.  Methods only needed
in later iterations (ensure_skill, list_active_skills) raise
NotImplementedError by default so IT-0 providers are not burdened with
implementations they don't need yet.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SandboxHandle:
    """Opaque reference to a live sandbox session.

    Passed between the provider and the tool factory so neither side
    needs to know the other's internals.
    """

    sandbox_id: str
    working_dir: str
    provider_name: str
    metadata: dict = field(default_factory=dict)


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
    def create_sandbox(self, working_dir: str, **kwargs) -> SandboxHandle:
        """Initialise a new sandbox and return a handle to it."""

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
        on_stdout: Callable[[str], None] | None = None,
    ) -> str:
        """Execute *code* inside the sandbox and return combined stdout/stderr.

        Args:
            handle:    Active sandbox handle.
            code:      Source code to execute.
            language:  Language identifier (e.g. ``"python"``, ``"javascript"``).
                       Must be one of the values returned by
                       :meth:`get_supported_languages`.
            on_stdout: Optional callback invoked with each stdout line as it
                       arrives.  Useful for streaming live output to the caller
                       (e.g. via SSE).  Called from the same thread as
                       ``run_code`` — the implementation must be non-blocking.
        """

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
        """Return the names of all files currently in the sandbox workspace."""

    # ------------------------------------------------------------------
    # Skill activation (IT-3 — not required for IT-0)
    # ------------------------------------------------------------------

    def ensure_skill(self, handle: SandboxHandle, skill: Any) -> None:
        """Install a skill's runtime dependencies into the sandbox.

        Concrete implementation is deferred to IT-3.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support skill activation yet."
        )

    def list_active_skills(self, handle: SandboxHandle) -> list[str]:
        """Return the names of skills already activated in this sandbox.

        Concrete implementation is deferred to IT-3.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support skill activation yet."
        )
