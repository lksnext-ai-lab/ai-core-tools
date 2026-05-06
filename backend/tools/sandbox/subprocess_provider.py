"""
SubprocessProvider — sandbox backend that executes code in a local subprocess.

This provider replicates the original ``python_sandbox_tools.py`` behaviour
exactly.  It is intended for local development only; it does **not** isolate
LLM-generated code from the backend process environment.

.. warning::
    ``SubprocessProvider`` must **not** be the default in any deployment that
    serves multiple tenants or exposes the Public API.  Set
    ``SANDBOX_DEFAULT_PROVIDER=opensandbox`` in production ``.env`` files.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import uuid

from utils.logger import get_logger
from .provider import SandboxProvider, SandboxHandle

logger = get_logger(__name__)

MAX_OUTPUT_CHARS = 20_000
DEFAULT_TIMEOUT = 30  # seconds


class SubprocessProvider(SandboxProvider):
    """Sandbox provider that executes code in a subprocess."""

    PROVIDER_NAME = "subprocess"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def create_sandbox(self, working_dir: str, **kwargs) -> SandboxHandle:
        os.makedirs(working_dir, exist_ok=True)
        return SandboxHandle(
            sandbox_id=str(uuid.uuid4()),
            working_dir=working_dir,
            provider_name=self.PROVIDER_NAME,
        )

    def destroy_sandbox(self, handle: SandboxHandle) -> None:
        # The subprocess provider does not manage the working_dir lifetime;
        # that responsibility belongs to the caller (AgentExecutionService).
        pass

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run_code(self, handle: SandboxHandle, code: str) -> str:
        """Execute *code* in a subprocess under *handle.working_dir*."""
        working_dir = handle.working_dir
        script_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".py",
                dir=working_dir,
                delete=False,
                encoding="utf-8",
            ) as f:
                f.write(code)
                script_path = f.name

            logger.info("SubprocessProvider using interpreter: %s", sys.executable)

            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=DEFAULT_TIMEOUT,
                cwd=working_dir,
                env=os.environ.copy(),
            )

            output = result.stdout or ""
            if result.stderr:
                output += (
                    f"\n[stderr]\n{result.stderr}"
                    f"\n[sandbox] interpreter: {sys.executable}"
                )

            logger.info(
                "SubprocessProvider executed in %s (exit=%d, output_len=%d)",
                working_dir,
                result.returncode,
                len(output),
            )

        except subprocess.TimeoutExpired:
            output = f"[Error] Execution timed out after {DEFAULT_TIMEOUT} seconds."
            logger.warning("SubprocessProvider timed out in %s", working_dir)
        except Exception as exc:
            output = f"[Error] Failed to execute code: {exc}"
            logger.error(
                "SubprocessProvider unexpected error: %s", exc, exc_info=True
            )
        finally:
            if script_path and os.path.exists(script_path):
                try:
                    os.unlink(script_path)
                except OSError:
                    pass

        return output[:MAX_OUTPUT_CHARS]

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def write_file(self, handle: SandboxHandle, filename: str, content: bytes) -> None:
        path = os.path.join(handle.working_dir, filename)
        with open(path, "wb") as f:
            f.write(content)

    def read_file(self, handle: SandboxHandle, filename: str) -> bytes:
        path = os.path.join(handle.working_dir, filename)
        with open(path, "rb") as f:
            return f.read()

    def list_files(self, handle: SandboxHandle) -> list[str]:
        return os.listdir(handle.working_dir)

    # ------------------------------------------------------------------
    # Skill activation (IT-3)
    # ------------------------------------------------------------------

    def ensure_skill(self, handle: SandboxHandle, skill) -> None:
        """Record skill as active.

        SubprocessProvider cannot isolate dependencies from the backend
        environment, so this method only records activation state.  Real
        dependency installation is the responsibility of the operator who
        sets up the development environment.
        """
        active = handle.metadata.setdefault("active_skills", {})
        if skill.name not in active:
            active[skill.name] = {"provider": self.PROVIDER_NAME}
            logger.info(
                "SubprocessProvider: skill '%s' marked active (no isolation).",
                skill.name,
            )

    def list_active_skills(self, handle: SandboxHandle) -> list[str]:
        """Return names of skills recorded as active in this handle."""
        return sorted(handle.metadata.get("active_skills", {}).keys())
