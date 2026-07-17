"""
SubprocessProvider — sandbox backend that executes code in a local subprocess.

This provider replicates the original ``python_sandbox_tools.py`` behaviour
exactly.  It is intended for local development only; it does **not** isolate
LLM-generated code from the backend process environment.

.. warning::
    ``SubprocessProvider`` must **not** be the default in any deployment that
    serves multiple tenants or exposes the Public API.  Set
    ``SANDBOX_DEFAULT_PROVIDER=opensandbox`` in production ``.env`` files.

v2 changes (sandbox-v2-migration Phase 1):
- Environment variables are filtered through ``_safe_env()`` to prevent
  secret leaks into subprocess code (API keys, DB URIs, etc.).
- ``run_code`` honours ``timeout`` and ``max_output_chars`` parameters.
- Truncated output ends with ``[Output truncated at N characters]``.
- ``on_stderr`` callback is forwarded in real time (streaming path).
- ``list_files`` returns workspace-relative paths.
- ``create_sandbox`` accepts ``session_key`` and ``existing_sandbox_id``
  (resume not supported — always creates a fresh sandbox).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import uuid
import warnings
from collections.abc import Callable
from datetime import timedelta

import config as settings
from utils.logger import get_logger
from .provider import SandboxProvider, SandboxHandle

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Environment filtering — prevent backend secrets from leaking into code
# ---------------------------------------------------------------------------

BLOCKED_ENV_PATTERNS: tuple[str, ...] = (
    "API_KEY",
    "SECRET",
    "DATABASE_URI",
    "PASSWORD",
    "TOKEN",
    "PRIVATE_KEY",
    "SQLALCHEMY",
    "OPENAI",
    "ANTHROPIC",
    "MISTRAL",
    "LANGSMITH",
    "AICT_",
)


def _safe_env() -> dict[str, str]:
    """Return a filtered copy of ``os.environ`` with secret-looking vars removed.

    Any environment variable whose upper-cased name contains one of the
    ``BLOCKED_ENV_PATTERNS`` substrings is excluded.  A comma-separated
    explicit allowlist can be added via ``SANDBOX_SUBPROCESS_ALLOW_ENV``
    (e.g. ``PYTHONPATH,HOME``) — those variables are always included.
    """
    allow_extra: set[str] = {
        v.strip()
        for v in os.getenv("SANDBOX_SUBPROCESS_ALLOW_ENV", "").split(",")
        if v.strip()
    }
    result: dict[str, str] = {}
    for k, v in os.environ.items():
        if k in allow_extra:
            result[k] = v
            continue
        if not any(p in k.upper() for p in BLOCKED_ENV_PATTERNS):
            result[k] = v
    return result


class SubprocessProvider(SandboxProvider):
    """Sandbox provider that executes code in a subprocess."""

    PROVIDER_NAME = "subprocess"
    SUPPORTED_LANGUAGES: list[str] = ["python", "bash"]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def create_sandbox(
        self,
        working_dir: str,
        *,
        session_key: str | None = None,
        existing_sandbox_id: str | None = None,
    ) -> SandboxHandle:
        """Create a new local sandbox (resume is not supported by this provider)."""
        if existing_sandbox_id:
            logger.debug(
                "SubprocessProvider: resume not supported — ignoring existing_sandbox_id=%s",
                existing_sandbox_id,
            )
        os.makedirs(working_dir, exist_ok=True)
        return SandboxHandle(
            sandbox_id=str(uuid.uuid4()),
            working_dir=working_dir,
            provider_name=self.PROVIDER_NAME,
            session_key=session_key,
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
        timeout: int | None = None,
        max_output_chars: int | None = None,
        on_stdout: Callable[[str], None] | None = None,
        on_stderr: Callable[[str], None] | None = None,
    ) -> str:
        """Execute *code* in a subprocess under *handle.working_dir*.

        Python runs from a temporary script file. Bash runs through
        ``bash -lc`` in the sandbox working directory.

        When *on_stdout* is provided, each stdout line is forwarded to it in
        real time via a reader thread; stderr is still collected and appended
        to the final output string.  When *on_stdout* is ``None`` the
        implementation falls back to the simpler ``subprocess.run`` path.

        Output is truncated to *max_output_chars* characters and a marker
        appended when truncation occurs.
        """
        if language not in self.SUPPORTED_LANGUAGES:
            return (
                f"[Error] Language '{language}' is not supported by SubprocessProvider. "
                f"Supported languages: {self.SUPPORTED_LANGUAGES}"
            )

        effective_timeout: int = (
            timeout if timeout is not None else settings.SANDBOX_DEFAULT_TIMEOUT_S
        )
        effective_limit: int = (
            max_output_chars
            if max_output_chars is not None
            else settings.SANDBOX_MAX_OUTPUT_CHARS
        )

        working_dir = handle.working_dir
        script_path = None
        try:
            if language == "bash":
                command = ["bash", "-lc", code]
                interpreter_for_log = "bash"
            else:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    suffix=".py",
                    dir=working_dir,
                    delete=False,
                    encoding="utf-8",
                ) as f:
                    f.write(code)
                    script_path = f.name
                command = [sys.executable, script_path]
                interpreter_for_log = sys.executable

            logger.info("SubprocessProvider using interpreter: %s", interpreter_for_log)
            safe_env = _safe_env()

            if on_stdout is None and on_stderr is None:
                # Fast path: wait for completion and return all output at once.
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=effective_timeout,
                    cwd=working_dir,
                    env=safe_env,
                )
                output = result.stdout or ""
                if result.stderr:
                    output += f"\n[stderr]\n{result.stderr}\n[sandbox] interpreter: {interpreter_for_log}"
                logger.info(
                    "SubprocessProvider executed in %s (exit=%d, output_len=%d)",
                    working_dir,
                    result.returncode,
                    len(output),
                )
            else:
                # Streaming path: forward each stdout/stderr line via callbacks.
                proc = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=working_dir,
                    env=safe_env,
                )

                stdout_lines: list[str] = []
                stderr_lines: list[str] = []

                def _read_stdout() -> None:
                    assert proc.stdout is not None
                    for line in proc.stdout:
                        stdout_lines.append(line)
                        if on_stdout is not None:
                            try:
                                on_stdout(line)
                            except Exception:
                                pass

                def _read_stderr() -> None:
                    assert proc.stderr is not None
                    for line in proc.stderr:
                        stderr_lines.append(line)
                        if on_stderr is not None:
                            try:
                                on_stderr(line)
                            except Exception:
                                pass

                t_out = threading.Thread(target=_read_stdout, daemon=True)
                t_err = threading.Thread(target=_read_stderr, daemon=True)
                t_out.start()
                t_err.start()
                timed_out = not t_out.join(timeout=effective_timeout) or False
                if timed_out or t_out.is_alive():
                    proc.kill()
                    t_out.join()
                    t_err.join()
                    return (
                        f"[Error] Execution timed out after {effective_timeout} seconds."
                    )
                t_err.join(timeout=2)
                proc.wait()

                output = "".join(stdout_lines)
                if stderr_lines:
                    output += f"\n[stderr]\n{''.join(stderr_lines)}\n[sandbox] interpreter: {interpreter_for_log}"
                logger.info(
                    "SubprocessProvider (streaming) executed in %s (exit=%d, output_len=%d)",
                    working_dir,
                    proc.returncode,
                    len(output),
                )

        except subprocess.TimeoutExpired:
            output = f"[Error] Execution timed out after {effective_timeout} seconds."
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

        if len(output) > effective_limit:
            output = (
                output[:effective_limit]
                + f"\n[Output truncated at {effective_limit} characters]"
            )
        return output

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def write_file(self, handle: SandboxHandle, filename: str, content: bytes) -> None:
        path = os.path.join(handle.working_dir, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(content)

    def read_file(self, handle: SandboxHandle, filename: str) -> bytes:
        path = os.path.join(handle.working_dir, filename)
        with open(path, "rb") as f:
            return f.read()

    def list_files(self, handle: SandboxHandle) -> list[str]:
        """Return workspace-relative paths of all files in the working directory."""
        working_dir = handle.working_dir
        result: list[str] = []
        for dirpath, dirnames, filenames in os.walk(working_dir):
            for fname in filenames:
                full_path = os.path.join(dirpath, fname)
                rel = os.path.relpath(full_path, working_dir)
                result.append(rel)
        return result
