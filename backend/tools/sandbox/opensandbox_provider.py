"""
OpenSandboxProvider — sandbox backend backed by the OpenSandbox server.

This is the **primary self-hosted provider** recommended for any deployment
that serves multiple tenants or exposes the Public API.  It runs each
conversation sandbox inside an isolated container via the OpenSandbox server
(https://github.com/open-sandbox/open-sandbox), preventing LLM-generated
code from accessing backend secrets or the host filesystem.

Requirements
------------
Install the optional dependency group::

    pip install opensandbox>=0.1.7 opensandbox-code-interpreter>=0.1.2

Configuration (env vars)
------------------------
``OPENSANDBOX_DOMAIN``
    OpenSandbox server ``host:port`` (e.g. ``opensandbox:8080`` when running
    with Docker Compose).  Falls back to ``localhost:8080``.

``OPENSANDBOX_API_KEY``
    Shared secret for the OpenSandbox server.  Leave empty for unauthenticated
    local deployments.

``SANDBOX_DEFAULT_TIMEOUT_S``
    Per-execution timeout in seconds (default: 30).

``SANDBOX_SESSION_TTL_H``
    Maximum sandbox lifetime in hours (default: 2).  After this the container
    is automatically reaped by the OpenSandbox server.

The sandbox container image is ``opensandbox/code-interpreter:v1.0.2`` (or
overridden via ``OPENSANDBOX_CODE_INTERPRETER_IMAGE``).

Workspace convention
--------------------
All user-facing files live under ``/workspace`` inside the container.
``write_file`` and ``read_file`` accept *bare filenames* and prepend the
workspace prefix automatically.  ``list_files`` returns bare filenames only.
"""

from __future__ import annotations

import os
from datetime import timedelta
from typing import TYPE_CHECKING

from utils.logger import get_logger
from .provider import SandboxProvider, SandboxHandle

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SANDBOX_WORKSPACE = "/workspace"

_DEFAULT_IMAGE = "opensandbox/code-interpreter:v1.0.2"

_ENV_DOMAIN = "OPENSANDBOX_DOMAIN"
_ENV_API_KEY = "OPENSANDBOX_API_KEY"
_ENV_IMAGE = "OPENSANDBOX_CODE_INTERPRETER_IMAGE"
_ENV_TIMEOUT_S = "SANDBOX_DEFAULT_TIMEOUT_S"
_ENV_TTL_H = "SANDBOX_SESSION_TTL_H"

MAX_OUTPUT_CHARS = 20_000

# ---------------------------------------------------------------------------
# Metadata keys stored inside SandboxHandle.metadata
# ---------------------------------------------------------------------------

_META_SANDBOX = "_sandbox"          # SandboxSync instance
_META_INTERPRETER = "_interpreter"  # CodeInterpreterSync instance
_META_CONTEXT = "_context"          # CodeContextSync instance


def _workspace_path(filename: str) -> str:
    """Return an absolute /workspace path for bare or workspace-prefixed input."""
    import posixpath

    normalized = posixpath.normpath(filename)
    if normalized.startswith(f"{_SANDBOX_WORKSPACE}/"):
        return normalized
    if normalized.startswith("/"):
        raise ValueError(f"Remote path must be inside {_SANDBOX_WORKSPACE}: {filename}")
    candidate = posixpath.normpath(f"{_SANDBOX_WORKSPACE}/{normalized}")
    if candidate != _SANDBOX_WORKSPACE and candidate.startswith(f"{_SANDBOX_WORKSPACE}/"):
        return candidate
    raise ValueError(f"Remote path must be inside {_SANDBOX_WORKSPACE}: {filename}")


def _get_connection_config():
    """Build a ``ConnectionConfigSync`` from the current environment."""
    try:
        from opensandbox.config.connection_sync import ConnectionConfigSync
    except ImportError as exc:
        raise RuntimeError(
            "OpenSandboxProvider requires the 'opensandbox' package.  "
            "Install it with: pip install opensandbox>=0.1.7"
        ) from exc

    domain = os.getenv(_ENV_DOMAIN, "localhost:8080")
    api_key = os.getenv(_ENV_API_KEY) or None

    return ConnectionConfigSync(
        domain=domain,
        api_key=api_key,
        # Use server proxy so the SDK routes execd requests through the
        # OpenSandbox API server rather than directly to the container port.
        # This is required in Docker Compose setups where the backend cannot
        # reach sandbox container ports directly.
        use_server_proxy=True,
    )


def _execution_timeout() -> int:
    """Return per-execution timeout in seconds (from env, default 30)."""
    try:
        return int(os.getenv(_ENV_TIMEOUT_S, "30"))
    except (ValueError, TypeError):
        return 30


def _session_ttl() -> timedelta:
    """Return sandbox lifetime (from env, default 2 hours)."""
    try:
        hours = float(os.getenv(_ENV_TTL_H, "2"))
    except (ValueError, TypeError):
        hours = 2.0
    return timedelta(hours=hours)


def _sandbox_image() -> str:
    return os.getenv(_ENV_IMAGE, _DEFAULT_IMAGE)


# ---------------------------------------------------------------------------
# Provider implementation
# ---------------------------------------------------------------------------


class OpenSandboxProvider(SandboxProvider):
    """Sandbox provider that executes code inside an isolated OpenSandbox container.

    Each call to :meth:`create_sandbox` spins up a new container via the
    OpenSandbox server and creates a persistent Python code-interpreter context.
    State (variables, installed packages, working directory) survives across
    :meth:`run_code` calls for the lifetime of the sandbox.

    File I/O uses the ``/workspace`` directory inside the container.  Files are
    addressed by bare filename (e.g. ``"report.xlsx"``), not absolute paths.

    Cleanup is performed by :meth:`destroy_sandbox` (called by
    :class:`~services.sandbox_session_service.SandboxSessionService` on
    conversation reset or agent deletion).
    """

    PROVIDER_NAME = "opensandbox"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def create_sandbox(self, working_dir: str, **kwargs) -> SandboxHandle:
        """Create a new isolated sandbox container and a persistent Python context.

        Args:
            working_dir: Host-side working directory.  Not used for file I/O by
                this provider (the container has its own ``/workspace``), but it
                is stored on the handle for compatibility with other layers.

        Returns:
            A populated :class:`~tools.sandbox.provider.SandboxHandle`.

        Raises:
            RuntimeError: If the ``opensandbox`` package is not installed.
            opensandbox.exceptions.SandboxException: If the server is unreachable
                or sandbox creation fails.
        """
        try:
            from opensandbox.sync.sandbox import SandboxSync
            from code_interpreter.sync.code_interpreter import CodeInterpreterSync
            from code_interpreter.models.code import SupportedLanguage
        except ImportError as exc:
            raise RuntimeError(
                "OpenSandboxProvider requires 'opensandbox' and "
                "'opensandbox-code-interpreter' packages.  "
                "Install them with: "
                "pip install opensandbox>=0.1.7 opensandbox-code-interpreter>=0.1.2"
            ) from exc

        config = _get_connection_config()
        image = _sandbox_image()
        ttl = _session_ttl()

        logger.info(
            "OpenSandboxProvider: creating sandbox (image=%s, ttl=%s)",
            image,
            ttl,
        )

        sandbox = SandboxSync.create(
            image,
            timeout=ttl,
            resource={"cpu": "1", "memory": "2Gi"},
            env={"PYTHONPATH": _SANDBOX_WORKSPACE},
            connection_config=config,
        )

        logger.info("OpenSandboxProvider: sandbox %s created, building interpreter", sandbox.id)

        interpreter = CodeInterpreterSync.create(sandbox=sandbox)
        context = interpreter.codes.create_context(SupportedLanguage.PYTHON)

        logger.info(
            "OpenSandboxProvider: interpreter ready (sandbox_id=%s, context_id=%s)",
            sandbox.id,
            context.id,
        )

        return SandboxHandle(
            sandbox_id=sandbox.id,
            working_dir=working_dir,
            provider_name=self.PROVIDER_NAME,
            metadata={
                _META_SANDBOX: sandbox,
                _META_INTERPRETER: interpreter,
                _META_CONTEXT: context,
            },
        )

    def destroy_sandbox(self, handle: SandboxHandle) -> None:
        """Kill the remote container and release local HTTP resources."""
        sandbox = handle.metadata.get(_META_SANDBOX)
        if sandbox is None:
            logger.warning(
                "OpenSandboxProvider.destroy_sandbox: no sandbox object in handle "
                "(sandbox_id=%s) — nothing to clean up",
                handle.sandbox_id,
            )
            return

        try:
            sandbox.kill()
            logger.info(
                "OpenSandboxProvider: sandbox %s killed", handle.sandbox_id
            )
        except Exception as exc:
            logger.warning(
                "OpenSandboxProvider: error killing sandbox %s: %s",
                handle.sandbox_id,
                exc,
            )
        finally:
            try:
                sandbox.close()
            except Exception as exc:
                logger.debug(
                    "OpenSandboxProvider: error closing sandbox %s transport: %s",
                    handle.sandbox_id,
                    exc,
                )

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run_code(self, handle: SandboxHandle, code: str) -> str:
        """Execute *code* inside the sandbox and return combined stdout/result text.

        The execution context persists across calls — variables, imports, and
        installed packages survive for the sandbox lifetime.

        Returns:
            Truncated combined output string (stdout + results + stderr on error).
        """
        interpreter = handle.metadata.get(_META_INTERPRETER)
        context = handle.metadata.get(_META_CONTEXT)

        if interpreter is None or context is None:
            return "[Error] OpenSandbox interpreter not initialised for this sandbox."

        timeout_s = _execution_timeout()

        try:
            execution = interpreter.codes.run(code, context=context)
        except Exception as exc:
            logger.error(
                "OpenSandboxProvider.run_code error (sandbox_id=%s): %s",
                handle.sandbox_id,
                exc,
                exc_info=True,
            )
            return f"[Error] Code execution failed: {exc}"[:MAX_OUTPUT_CHARS]

        # Collect output: use the ``text`` property which combines stdout +
        # result text, then append stderr/error if present.
        output_parts: list[str] = []

        combined = execution.text
        if combined:
            output_parts.append(combined)

        if execution.error is not None:
            err_text = (
                f"\n[Error] {execution.error.name}: {execution.error.value}"
                if hasattr(execution.error, "name")
                else f"\n[Error] {execution.error}"
            )
            output_parts.append(err_text)

        stderr_lines = execution.logs.stderr if execution.logs else []
        if stderr_lines:
            stderr_text = "\n".join(
                line.text for line in stderr_lines if hasattr(line, "text")
            )
            if stderr_text.strip():
                output_parts.append(f"\n[stderr]\n{stderr_text}")

        output = "\n".join(output_parts) if output_parts else ""

        logger.info(
            "OpenSandboxProvider.run_code: sandbox=%s exit_code=%s output_len=%d",
            handle.sandbox_id,
            execution.exit_code,
            len(output),
        )

        return output[:MAX_OUTPUT_CHARS]

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def write_file(self, handle: SandboxHandle, filename: str, content: bytes) -> None:
        """Write *content* bytes to ``/workspace/{filename}`` in the sandbox."""
        sandbox = handle.metadata.get(_META_SANDBOX)
        if sandbox is None:
            raise RuntimeError(
                f"OpenSandboxProvider: no sandbox for handle {handle.sandbox_id}"
            )
        remote_path = _workspace_path(filename)
        sandbox.files.write_file(remote_path, content)
        logger.debug(
            "OpenSandboxProvider.write_file: wrote %d bytes to %s (sandbox=%s)",
            len(content),
            remote_path,
            handle.sandbox_id,
        )

    def read_file(self, handle: SandboxHandle, filename: str) -> bytes:
        """Return raw bytes of ``/workspace/{filename}`` from the sandbox."""
        sandbox = handle.metadata.get(_META_SANDBOX)
        if sandbox is None:
            raise RuntimeError(
                f"OpenSandboxProvider: no sandbox for handle {handle.sandbox_id}"
            )
        remote_path = _workspace_path(filename)
        data = sandbox.files.read_bytes(remote_path)
        logger.debug(
            "OpenSandboxProvider.read_file: read %d bytes from %s (sandbox=%s)",
            len(data),
            remote_path,
            handle.sandbox_id,
        )
        return data

    def list_files(self, handle: SandboxHandle) -> list[str]:
        """Return bare filenames of all files under ``/workspace`` in the sandbox.

        Directories are excluded; only files are returned.
        """
        sandbox = handle.metadata.get(_META_SANDBOX)
        if sandbox is None:
            raise RuntimeError(
                f"OpenSandboxProvider: no sandbox for handle {handle.sandbox_id}"
            )

        try:
            from opensandbox.models.filesystem import SearchEntry
        except ImportError as exc:
            raise RuntimeError(
                "OpenSandboxProvider requires the 'opensandbox' package."
            ) from exc

        try:
            entries = sandbox.files.search(
                SearchEntry(path=_SANDBOX_WORKSPACE, pattern="*")
            )
        except Exception as exc:
            logger.warning(
                "OpenSandboxProvider.list_files: search failed (sandbox=%s): %s",
                handle.sandbox_id,
                exc,
            )
            return []

        filenames: list[str] = []
        for entry in entries:
            # Include only regular files (size > 0 or size is None — directories
            # typically have size == 0, but we check by path not having a trailing /)
            path = entry.path
            if path and not path.endswith("/"):
                # Return bare filename relative to workspace
                basename = os.path.basename(path)
                if basename:
                    filenames.append(basename)

        logger.debug(
            "OpenSandboxProvider.list_files: found %d files (sandbox=%s)",
            len(filenames),
            handle.sandbox_id,
        )
        return filenames
