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
    """Abstract base class for sandbox execution backends."""

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
    def run_code(self, handle: SandboxHandle, code: str) -> str:
        """Execute *code* inside the sandbox and return combined stdout/stderr."""

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
