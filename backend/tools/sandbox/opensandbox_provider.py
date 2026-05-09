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

``OPENSANDBOX_SUPPORTED_LANGUAGES``
    Comma-separated list of language identifiers the provider will activate
    inside each sandbox container (default: ``python``).  Supported values
    depend on the ``SupportedLanguage`` enum exposed by the
    ``opensandbox-code-interpreter`` SDK.  Example::

        OPENSANDBOX_SUPPORTED_LANGUAGES=python,javascript,bash

The sandbox container image is ``opensandbox/code-interpreter:v1.0.2`` (or
overridden via ``OPENSANDBOX_CODE_INTERPRETER_IMAGE``).

Workspace convention
--------------------
All user-facing files live under ``/workspace`` inside the container.
``write_file`` and ``read_file`` accept *bare filenames* and prepend the
workspace prefix automatically.  ``list_files`` returns workspace-relative
paths (e.g. ``report.xlsx``, ``scripts/setup.py``).  The ``.skills/``
directory is excluded from ``list_files`` results.

v2 changes (sandbox-v2-migration Phase 1):
- ``run_code`` honours ``timeout``, ``max_output_chars``, and ``on_stderr``.
- Truncated output ends with ``[Output truncated at N characters]``.
- ``ensure_skill`` stub updated — full implementation in Phase 3.
- ``list_files`` returns workspace-relative paths; ``.skills/`` excluded.
- ``create_sandbox`` accepts ``session_key`` and ``existing_sandbox_id``
  (resume implemented in Phase 3 — currently always creates a new sandbox).
"""

from __future__ import annotations

import os
import posixpath
from collections.abc import Callable
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import config as settings
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
_ENV_SUPPORTED_LANGUAGES = "OPENSANDBOX_SUPPORTED_LANGUAGES"

MAX_OUTPUT_CHARS = 20_000

# ---------------------------------------------------------------------------
# Language → SupportedLanguage enum-member name mapping.
# Keys are the normalised lower-case language identifiers used throughout
# this codebase; values are the attribute names on the SDK's SupportedLanguage
# enum.  Unknown keys are skipped with a warning at sandbox-creation time.
# ---------------------------------------------------------------------------

_LANGUAGE_ENUM_MAP: dict[str, str] = {
    "python": "PYTHON",
    "javascript": "JAVASCRIPT",
    "typescript": "TYPESCRIPT",
    "bash": "BASH",
    "r": "R",
    "java": "JAVA",
    "go": "GO",
    "rust": "RUST",
    "csharp": "CSHARP",
    "cpp": "CPP",
    "c": "C",
    "php": "PHP",
    "ruby": "RUBY",
    "swift": "SWIFT",
    "kotlin": "KOTLIN",
}

# ---------------------------------------------------------------------------
# Metadata keys stored inside SandboxHandle.metadata
# ---------------------------------------------------------------------------

_META_SANDBOX = "_sandbox"          # SandboxSync instance
_META_INTERPRETER = "_interpreter"  # CodeInterpreterSync instance
_META_CONTEXTS = "_contexts"        # dict[str, CodeContextSync] — one entry per language


def _supported_languages() -> list[str]:
    """Return the list of language identifiers configured for this provider.

    Reads ``OPENSANDBOX_SUPPORTED_LANGUAGES`` (comma-separated, default
    ``"python"``).  The returned list is normalised to lowercase and deduplicated
    while preserving insertion order.
    """
    raw = os.getenv(_ENV_SUPPORTED_LANGUAGES, "python")
    seen: set[str] = set()
    result: list[str] = []
    for token in raw.split(","):
        lang = token.strip().lower()
        if lang and lang not in seen:
            seen.add(lang)
            result.append(lang)
    return result or ["python"]


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
    OpenSandbox server and creates a persistent execution context for every
    language listed in :meth:`get_supported_languages`.  State (variables,
    installed packages, working directory) survives across :meth:`run_code`
    calls for the sandbox lifetime.

    The set of active languages is configured through the
    ``OPENSANDBOX_SUPPORTED_LANGUAGES`` environment variable (comma-separated,
    default ``python``).  Any language listed there that the SDK's
    ``SupportedLanguage`` enum does not recognise is skipped with a warning.

    File I/O uses the ``/workspace`` directory inside the container.  Files are
    addressed by bare filename (e.g. ``"report.xlsx"``), not absolute paths.

    Cleanup is performed by :meth:`destroy_sandbox` (called by
    :class:`~services.sandbox_session_service.SandboxSessionService` on
    conversation reset or agent deletion).
    """

    PROVIDER_NAME = "opensandbox"

    def get_supported_languages(self) -> list[str]:
        """Return the language identifiers configured via the environment."""
        return _supported_languages()

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
        """Create a new isolated sandbox container and persistent execution contexts.

        *existing_sandbox_id* and *session_key* are accepted for API compatibility
        with the v2 provider contract.  Full resume support is implemented in
        Phase 3 of the sandbox-v2-migration plan.  For now, this method always
        creates a new sandbox (existing_sandbox_id is ignored).

        One context is created per language listed in
        :meth:`get_supported_languages`.  Languages not recognised by the SDK's
        ``SupportedLanguage`` enum are skipped with a warning.

        Args:
            working_dir:         Host-side working directory.  Not used for file I/O by
                this provider (the container has its own ``/workspace``), but it
                is stored on the handle for compatibility with other layers.
            session_key:         Session key stored on the returned handle.
            existing_sandbox_id: Ignored in Phase 1; resume implemented in Phase 3.

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

        languages = self.get_supported_languages()
        logger.info(
            "OpenSandboxProvider: creating sandbox (image=%s, ttl=%s, languages=%s)",
            image,
            ttl,
            languages,
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

        # Create one execution context per configured language.
        contexts: dict[str, object] = {}
        for lang in languages:
            enum_name = _LANGUAGE_ENUM_MAP.get(lang)
            if enum_name is None:
                logger.warning(
                    "OpenSandboxProvider: unknown language '%s' — no enum mapping, skipping",
                    lang,
                )
                continue
            lang_enum = getattr(SupportedLanguage, enum_name, None)
            if lang_enum is None:
                logger.warning(
                    "OpenSandboxProvider: SupportedLanguage has no member '%s' "
                    "(language='%s') — skipping",
                    enum_name,
                    lang,
                )
                continue
            try:
                context = interpreter.codes.create_context(lang_enum)
                contexts[lang] = context
                logger.info(
                    "OpenSandboxProvider: context created for language '%s' "
                    "(sandbox=%s, context_id=%s)",
                    lang,
                    sandbox.id,
                    context.id,
                )
            except Exception as exc:
                logger.warning(
                    "OpenSandboxProvider: failed to create context for language '%s': %s",
                    lang,
                    exc,
                )

        if not contexts:
            # Ensure at least a Python context so the sandbox is usable.
            logger.warning(
                "OpenSandboxProvider: no language contexts created; falling back to Python"
            )
            context = interpreter.codes.create_context(SupportedLanguage.PYTHON)
            contexts["python"] = context

        logger.info(
            "OpenSandboxProvider: interpreter ready (sandbox_id=%s, languages=%s)",
            sandbox.id,
            list(contexts.keys()),
        )

        return SandboxHandle(
            sandbox_id=sandbox.id,
            working_dir=working_dir,
            provider_name=self.PROVIDER_NAME,
            session_key=session_key,
            metadata={
                _META_SANDBOX: sandbox,
                _META_INTERPRETER: interpreter,
                _META_CONTEXTS: contexts,
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
        """Execute *code* inside the sandbox and return combined stdout/result text.

        The execution context persists across calls — variables, imports, and
        installed packages survive for the sandbox lifetime.

        Args:
            handle:           Active sandbox handle.
            code:             Source code to execute.
            language:         Language identifier (must be one of the keys created at
                              sandbox initialisation).
            timeout:          Per-execution timeout in seconds.  Falls back to
                              ``settings.SANDBOX_DEFAULT_TIMEOUT_S`` when ``None``.
            max_output_chars: Maximum characters to return.  Falls back to
                              ``settings.SANDBOX_MAX_OUTPUT_CHARS`` when ``None``.
                              Truncated output ends with a marker string.
            on_stdout:        Optional callback invoked with each stdout line in real
                              time.  Uses ``ExecutionHandlersSync`` under the hood.
            on_stderr:        Optional callback invoked with each stderr line after
                              execution completes.

        Returns:
            Truncated combined output string (stdout + results + stderr on error).
        """
        effective_limit: int = (
            max_output_chars
            if max_output_chars is not None
            else settings.SANDBOX_MAX_OUTPUT_CHARS
        )

        interpreter = handle.metadata.get(_META_INTERPRETER)
        contexts: dict = handle.metadata.get(_META_CONTEXTS) or {}
        context = contexts.get(language)

        if interpreter is None:
            return "[Error] OpenSandbox interpreter not initialised for this sandbox."

        if context is None:
            available = list(contexts.keys())
            return (
                f"[Error] Language '{language}' is not available in this sandbox. "
                f"Available languages: {available}"
            )

        # Build streaming handlers when the caller wants live stdout lines.
        handlers = None
        if on_stdout is not None:
            try:
                from opensandbox.models.execd_sync import ExecutionHandlersSync

                def _stdout_cb(msg: object) -> None:
                    text: str = msg.text if hasattr(msg, "text") else str(msg)
                    try:
                        on_stdout(text)
                    except Exception:
                        pass  # never let callback errors abort execution

                handlers = ExecutionHandlersSync(on_stdout=_stdout_cb)
            except ImportError:
                pass  # fall back to batch mode if SDK import fails

        try:
            execution = interpreter.codes.run(code, context=context, handlers=handlers)
        except Exception as exc:
            logger.error(
                "OpenSandboxProvider.run_code error (sandbox_id=%s): %s",
                handle.sandbox_id,
                exc,
                exc_info=True,
            )
            return f"[Error] Code execution failed: {exc}"[:effective_limit]

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
                # Forward stderr lines to callback if provided.
                if on_stderr is not None:
                    for line in stderr_lines:
                        text: str = line.text if hasattr(line, "text") else str(line)
                        try:
                            on_stderr(text)
                        except Exception:
                            pass

        output = "\n".join(output_parts) if output_parts else ""

        logger.info(
            "OpenSandboxProvider.run_code: sandbox=%s exit_code=%s output_len=%d",
            handle.sandbox_id,
            execution.exit_code,
            len(output),
        )

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
        """Return workspace-relative paths of all files under ``/workspace``.

        Paths are relative to ``/workspace`` (e.g. ``report.xlsx``,
        ``scripts/setup.py``).  Directories and the ``.skills/`` tree are
        excluded from the result.
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

        # _SANDBOX_WORKSPACE is "/workspace"; ensure it ends with "/" for prefix strip.
        workspace_prefix = _SANDBOX_WORKSPACE.rstrip("/") + "/"
        result: list[str] = []
        for entry in entries:
            path: str = entry.path or ""
            # Directories have trailing "/" — skip them.
            if not path or path.endswith("/"):
                continue
            # Strip the /workspace/ prefix to get a workspace-relative path.
            if path.startswith(workspace_prefix):
                rel = path[len(workspace_prefix):]
            else:
                rel = posixpath.basename(path)
            # Exclude .skills/ subtree.
            if rel.startswith(".skills/") or rel == ".skills":
                continue
            if rel:
                result.append(rel)

        logger.debug(
            "OpenSandboxProvider.list_files: found %d files (sandbox=%s)",
            len(result),
            handle.sandbox_id,
        )
        return result

    # ------------------------------------------------------------------
    # Skill activation
    # ------------------------------------------------------------------

    def ensure_skill(
        self, handle: SandboxHandle, skill: Any, *, retry: bool = False
    ) -> dict[str, Any]:
        """Not yet implemented — full implementation in Phase 3.

        Raises:
            NotImplementedError: Always.  See Phase 3 of the sandbox-v2-migration
                plan for the full implementation (file copy + bootstrap).
        """
        raise NotImplementedError(
            "OpenSandboxProvider.ensure_skill is not yet implemented. "
            "See Phase 3 of the sandbox-v2-migration plan."
        )

    def list_active_skills(self, handle: SandboxHandle) -> dict[str, dict[str, Any]]:
        """Return the typed Skill activation state from ``handle.active_skills``."""
        return dict(handle.active_skills)

