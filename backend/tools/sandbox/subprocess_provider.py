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
import threading
import uuid
from collections.abc import Callable

from utils.logger import get_logger
from .provider import SandboxProvider, SandboxHandle

logger = get_logger(__name__)

MAX_OUTPUT_CHARS = 20_000
DEFAULT_TIMEOUT = 30  # seconds


class SubprocessProvider(SandboxProvider):
    """Sandbox provider that executes code in a subprocess."""

    PROVIDER_NAME = "subprocess"
    SUPPORTED_LANGUAGES: list[str] = ["python"]

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

    def run_code(
        self,
        handle: SandboxHandle,
        code: str,
        *,
        language: str = "python",
        on_stdout: Callable[[str], None] | None = None,
    ) -> str:
        """Execute *code* in a subprocess under *handle.working_dir*.

        Only ``"python"`` is supported.  Requests for other languages return an
        error string so the LLM can surface a meaningful message to the user.

        When *on_stdout* is provided, each stdout line is forwarded to it in
        real time via a reader thread; stderr is still collected and appended
        to the final output string.  When *on_stdout* is ``None`` the
        implementation falls back to the simpler ``subprocess.run`` path.
        """
        if language not in self.SUPPORTED_LANGUAGES:
            return (
                f"[Error] Language '{language}' is not supported by SubprocessProvider. "
                f"Supported languages: {self.SUPPORTED_LANGUAGES}"
            )

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

            if on_stdout is None:
                # Fast path: wait for completion and return all output at once.
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
            else:
                # Streaming path: forward each stdout line via on_stdout callback.
                proc = subprocess.Popen(
                    [sys.executable, script_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=working_dir,
                    env=os.environ.copy(),
                )

                stdout_lines: list[str] = []
                stderr_lines: list[str] = []

                def _read_stdout() -> None:
                    assert proc.stdout is not None
                    for line in proc.stdout:
                        stdout_lines.append(line)
                        try:
                            on_stdout(line)
                        except Exception:
                            pass

                def _read_stderr() -> None:
                    assert proc.stderr is not None
                    for line in proc.stderr:
                        stderr_lines.append(line)

                t_out = threading.Thread(target=_read_stdout, daemon=True)
                t_err = threading.Thread(target=_read_stderr, daemon=True)
                t_out.start()
                t_err.start()
                timed_out = not t_out.join(timeout=DEFAULT_TIMEOUT) or False
                if timed_out or t_out.is_alive():
                    proc.kill()
                    t_out.join()
                    t_err.join()
                    return f"[Error] Execution timed out after {DEFAULT_TIMEOUT} seconds."
                t_err.join(timeout=2)
                proc.wait()

                output = "".join(stdout_lines)
                if stderr_lines:
                    output += (
                        f"\n[stderr]\n{''.join(stderr_lines)}"
                        f"\n[sandbox] interpreter: {sys.executable}"
                    )
                logger.info(
                    "SubprocessProvider (streaming) executed in %s (exit=%d, output_len=%d)",
                    working_dir,
                    proc.returncode,
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
