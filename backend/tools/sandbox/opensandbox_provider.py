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
    inside each sandbox container (default: ``python,bash``).  Supported values
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
import queue
import threading
import time
from contextvars import copy_context
from collections.abc import Callable
from datetime import timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import config as settings
from utils.logger import get_logger
from .provider import SandboxProvider, SandboxHandle, SandboxExpiredError

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Module-level SDK import — makes SandboxSync a patchable name for tests.
# Falls back to None when the opensandbox package is absent so that the module
# can still be imported (methods raise RuntimeError on actual use).
# ---------------------------------------------------------------------------
try:
    from opensandbox.sync.sandbox import SandboxSync  # type: ignore[import]
    from opensandbox.exceptions import (  # type: ignore[import]
        SandboxApiException,
        SandboxUnhealthyException,
        SandboxReadyTimeoutException,
    )
    _SDK_EXPIRY_EXCEPTIONS: tuple = (
        SandboxApiException,
        SandboxUnhealthyException,
        SandboxReadyTimeoutException,
    )
except ImportError:
    SandboxSync = None  # type: ignore[assignment,misc]
    SandboxApiException = None  # type: ignore[assignment]
    SandboxUnhealthyException = None  # type: ignore[assignment]
    SandboxReadyTimeoutException = None  # type: ignore[assignment]
    _SDK_EXPIRY_EXCEPTIONS = ()

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

_BOOTSTRAP_EXIT_PREFIX = "__AICT_BOOTSTRAP_EXIT_CODE__="

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
_META_CONTEXT_POOLS = "_context_pools"        # dict[str, list[dict]] — pooled execution contexts
_META_CONTEXT_LANG_ENUMS = "_context_lang_enums"  # dict[str, SupportedLanguage] used for new contexts
_META_CONTEXT_POOL_LOCK = "_context_pool_lock"    # threading.Lock guarding pool growth


def _supported_languages() -> list[str]:
    """Return the list of language identifiers configured for this provider.

    Reads ``OPENSANDBOX_SUPPORTED_LANGUAGES`` (comma-separated, default
    ``"python,bash"``).  The returned list is normalised to lowercase and deduplicated
    while preserving insertion order.
    """
    raw = os.getenv(_ENV_SUPPORTED_LANGUAGES, "python,bash")
    seen: set[str] = set()
    result: list[str] = []
    for token in raw.split(","):
        lang = token.strip().lower()
        if lang and lang not in seen:
            seen.add(lang)
            result.append(lang)
    return result or ["python", "bash"]


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


def _max_contexts_per_language() -> int:
    """Return OpenSandbox context pool size per language.

    A single OpenSandbox code context maps to one interpreter session. Running
    two snippets against the same context concurrently can raise
    ``RUNTIME_ERROR: ... session is busy``. A small pool lets independent tool
    calls run in parallel while preserving the primary context for normal
    sequential REPL usage.
    """
    try:
        configured = int(getattr(settings, "OPENSANDBOX_MAX_CONTEXTS_PER_LANGUAGE", 4))
    except (TypeError, ValueError):
        configured = 4
    return max(1, configured)


# ---------------------------------------------------------------------------
# Skill activation helpers (Phase 3 step 3.7)
# ---------------------------------------------------------------------------


def _healthy_for_sandbox(state: dict | None, sandbox_id: str) -> bool:
    """Return True if *state* is healthy for *sandbox_id*.

    Both phases must be ``"ok"`` or ``"skipped"`` and the state must have been
    recorded for the same sandbox id.
    """
    if not state:
        return False
    if state.get("sandbox_id") != sandbox_id:
        return False
    phases = state.get("phases", {})
    files_ok = phases.get("files") == "ok"
    bootstrap_ok = phases.get("bootstrap") in ("ok", "skipped")
    return files_ok and bootstrap_ok


def _write_skill_files(
    provider: "OpenSandboxProvider",
    handle: SandboxHandle,
    skill: Any,
    files_dir: str,
) -> None:
    """Write all SkillFile records for *skill* into the sandbox under *files_dir*."""
    for skill_file in skill.files:
        if str(skill_file.path).endswith("/"):
            logger.debug(
                "OpenSandboxProvider.ensure_skill: skipping directory placeholder %s",
                skill_file.path,
            )
            continue
        dest_path = f"{files_dir}/{skill_file.path}"
        content = skill_file.content_bytes or (
            skill_file.content_text.encode("utf-8") if skill_file.content_text else b""
        )
        provider.write_file(handle, dest_path, content)


def _read_skill_file_text(skill: Any, relative_path: str) -> str:
    """Return the text content of one SkillFile by its package-root-relative path."""
    for sf in skill.files:
        if sf.path == relative_path:
            if sf.content_text is not None:
                return sf.content_text
            if sf.content_bytes is not None:
                return sf.content_bytes.decode("utf-8")
    raise FileNotFoundError(
        f"Bootstrap script '{relative_path}' not found in Skill '{skill.name}' package."
    )


def _bootstrap_language_for_path(path: str) -> str:
    """Infer the sandbox language for a Skill bootstrap script path."""
    suffix = posixpath.splitext(path.lower())[1]
    return {
        ".py": "python",
        ".js": "javascript",
        ".mjs": "javascript",
        ".cjs": "javascript",
        ".ts": "typescript",
        ".sh": "bash",
        ".bash": "bash",
    }.get(suffix, "python")


def _bootstrap_failed(output: str) -> bool:
    """Return True when run_code output indicates bootstrap execution failed."""
    if "[Error]" in output or "[stderr]" in output:
        return True
    for line in output.splitlines():
        if not line.startswith(_BOOTSTRAP_EXIT_PREFIX):
            continue
        try:
            return int(line.removeprefix(_BOOTSTRAP_EXIT_PREFIX).strip()) != 0
        except ValueError:
            return True
    return False


def _wrap_bootstrap_script(script: str, language: str) -> str:
    """Wrap bootstrap code so provider-visible output includes stderr and exit code."""
    if language != "bash":
        return script

    return (
        "(\n"
        "if [ -f /opt/opensandbox/code-interpreter-env.sh ]; then\n"
        "    source /opt/opensandbox/code-interpreter-env.sh python >/dev/null 2>&1 || true\n"
        "    source /opt/opensandbox/code-interpreter-env.sh node >/dev/null 2>&1 || true\n"
        "fi\n"
        "if ! command -v sudo >/dev/null 2>&1 && [ \"$(id -u)\" -eq 0 ]; then\n"
        "    sudo() { \"$@\"; }\n"
        "fi\n"
        "if command -v npm >/dev/null 2>&1; then\n"
        "    export NODE_PATH=\"$(npm root -g)${NODE_PATH:+:$NODE_PATH}\"\n"
        "fi\n"
        f"{script.rstrip()}\n"
        ") 2>&1\n"
        "__aict_bootstrap_exit_code=$?\n"
        f"printf '\\n{_BOOTSTRAP_EXIT_PREFIX}%s\\n' \"$__aict_bootstrap_exit_code\"\n"
        "exit \"$__aict_bootstrap_exit_code\"\n"
    )


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
    default ``python,bash``).  Any language listed there that the SDK's
    ``SupportedLanguage`` enum does not recognise is skipped with a warning.

    File I/O uses the ``/workspace`` directory inside the container.  Files are
    addressed by bare filename (e.g. ``"report.xlsx"``), not absolute paths.

    Cleanup is performed by :meth:`destroy_sandbox` (called by
    :class:`~services.sandbox_session_service.SandboxSessionService` on
    conversation reset or agent deletion).
    """

    PROVIDER_NAME = "opensandbox"

    def __init__(self) -> None:
        """Detect SDK resume/renew capability and store flags.

        Warnings are emitted at construction time when the installed SDK lacks
        ``SandboxSync.resume`` or ``SandboxSync.renew`` (Phase 3 step 3.1).
        """
        if SandboxSync is not None:
            self._can_resume = hasattr(SandboxSync, "resume")
            self._can_renew = hasattr(SandboxSync, "renew")
            if not self._can_resume:
                logger.warning(
                    "OpenSandbox SDK does not support SandboxSync.resume — "
                    "sandbox resume is disabled. All sessions will create new sandboxes."
                )
            if not self._can_renew:
                logger.warning(
                    "OpenSandbox SDK does not support sandbox.renew — "
                    "sandbox TTL extension is disabled."
                )
        else:
            self._can_resume = False
            self._can_renew = False

        self._capabilities = {"resume": self._can_resume, "renew": self._can_renew}
        # Expiry exception tuple; tests may patch this attribute directly.
        self._sdk_expiry_exceptions = _SDK_EXPIRY_EXCEPTIONS
        # Connection config cached after first use (tests may inject directly).
        self._connection_config = None

    def get_supported_languages(self) -> list[str]:
        """Return the language identifiers configured via the environment."""
        return _supported_languages()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_config(self):
        """Return (and cache) the connection config."""
        if self._connection_config is None:
            self._connection_config = _get_connection_config()
        return self._connection_config

    def _setup_sandbox_handle(
        self,
        sandbox: Any,
        working_dir: str,
        session_key: str | None,
    ) -> SandboxHandle:
        """Build interpreter + contexts for an SDK sandbox object and return a handle."""
        try:
            from code_interpreter.sync.code_interpreter import CodeInterpreterSync  # type: ignore[import]
            from code_interpreter.models.code import SupportedLanguage  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "OpenSandboxProvider requires 'opensandbox-code-interpreter'.  "
                "Install with: pip install opensandbox-code-interpreter>=0.1.2"
            ) from exc

        interpreter = CodeInterpreterSync.create(sandbox=sandbox)

        languages = self.get_supported_languages()
        contexts: dict[str, object] = {}
        context_lang_enums: dict[str, object] = {}
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
                context_lang_enums[lang] = lang_enum
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
            logger.warning(
                "OpenSandboxProvider: no language contexts created; falling back to Python"
            )
            context = interpreter.codes.create_context(SupportedLanguage.PYTHON)
            contexts["python"] = context
            context_lang_enums["python"] = SupportedLanguage.PYTHON

        logger.info(
            "OpenSandboxProvider: interpreter ready (sandbox_id=%s, languages=%s)",
            sandbox.id,
            list(contexts.keys()),
        )
        context_pools = {
            lang: [{"context": context, "lock": threading.Lock()}]
            for lang, context in contexts.items()
        }
        return SandboxHandle(
            sandbox_id=sandbox.id,
            working_dir=working_dir,
            provider_name=self.PROVIDER_NAME,
            session_key=session_key,
            metadata={
                _META_SANDBOX: sandbox,
                _META_INTERPRETER: interpreter,
                _META_CONTEXTS: contexts,
                _META_CONTEXT_POOLS: context_pools,
                _META_CONTEXT_LANG_ENUMS: context_lang_enums,
                _META_CONTEXT_POOL_LOCK: threading.Lock(),
                "provider_capabilities": self._capabilities,
            },
        )

    def _ensure_context_pools(self, handle: SandboxHandle) -> dict[str, list[dict[str, Any]]]:
        """Ensure older handles have pool metadata.

        Tests and resumed handles may only contain ``_META_CONTEXTS``. Convert
        those primary contexts into one-entry pools lazily so ``run_code`` can
        use the same acquisition path everywhere.
        """
        pools = handle.metadata.get(_META_CONTEXT_POOLS)
        if isinstance(pools, dict):
            handle.metadata.setdefault(_META_CONTEXT_POOL_LOCK, threading.Lock())
            handle.metadata.setdefault(_META_CONTEXT_LANG_ENUMS, {})
            return pools

        contexts: dict = handle.metadata.get(_META_CONTEXTS) or {}
        pools = {
            lang: [{"context": context, "lock": threading.Lock()}]
            for lang, context in contexts.items()
        }
        handle.metadata[_META_CONTEXT_POOLS] = pools
        handle.metadata.setdefault(_META_CONTEXT_POOL_LOCK, threading.Lock())
        handle.metadata.setdefault(_META_CONTEXT_LANG_ENUMS, {})
        return pools

    def _language_enum_for_context(self, handle: SandboxHandle, language: str) -> Any | None:
        """Return the SDK enum value required to create a new context."""
        lang_enums: dict = handle.metadata.setdefault(_META_CONTEXT_LANG_ENUMS, {})
        if language in lang_enums:
            return lang_enums[language]

        enum_name = _LANGUAGE_ENUM_MAP.get(language)
        if enum_name is None:
            return None

        try:
            from code_interpreter.models.code import SupportedLanguage  # type: ignore[import]
        except ImportError:
            return None

        lang_enum = getattr(SupportedLanguage, enum_name, None)
        if lang_enum is not None:
            lang_enums[language] = lang_enum
        return lang_enum

    def _create_context_pool_entry(
        self,
        handle: SandboxHandle,
        language: str,
    ) -> dict[str, Any] | None:
        """Create one additional execution context for *language*."""
        interpreter = handle.metadata.get(_META_INTERPRETER)
        if interpreter is None:
            return None

        lang_enum = self._language_enum_for_context(handle, language)
        if lang_enum is None:
            return None

        context = interpreter.codes.create_context(lang_enum)
        logger.info(
            "OpenSandboxProvider: additional context created for language '%s' "
            "(sandbox=%s, context_id=%s)",
            language,
            handle.sandbox_id,
            getattr(context, "id", "<unknown>"),
        )
        return {"context": context, "lock": threading.Lock()}

    def _acquire_context_entry(
        self,
        handle: SandboxHandle,
        language: str,
        wait_timeout: int | float,
    ) -> dict[str, Any] | None:
        """Acquire a free context for a code run, growing the pool when needed."""
        pools = self._ensure_context_pools(handle)
        pool_lock = handle.metadata.setdefault(_META_CONTEXT_POOL_LOCK, threading.Lock())
        deadline = time.monotonic() + max(float(wait_timeout), 1.0)
        max_contexts = _max_contexts_per_language()

        while True:
            with pool_lock:
                pool = pools.get(language, [])
                for entry in pool:
                    entry_lock = entry["lock"]
                    if entry_lock.acquire(blocking=False):
                        return entry

                if pool and len(pool) < max_contexts:
                    entry = self._create_context_pool_entry(handle, language)
                    if entry is not None:
                        entry["lock"].acquire(blocking=False)
                        pool.append(entry)
                        pools[language] = pool
                        return entry

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            time.sleep(min(0.05, remaining))

    def _release_context_entry(self, entry: dict[str, Any] | None) -> None:
        """Release a context entry acquired by ``_acquire_context_entry``."""
        if entry is None:
            return
        entry_lock = entry.get("lock")
        try:
            if entry_lock is not None and entry_lock.locked():
                entry_lock.release()
        except RuntimeError:
            pass

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
        """Create or resume an isolated sandbox container.

        When *existing_sandbox_id* is provided and the SDK supports
        ``SandboxSync.resume``, the provider attempts to reconnect to the
        existing container.  On any expiry or SDK error the method falls back
        to creating a fresh sandbox (Phase 3 step 3.2).

        Args:
            working_dir:         Host-side working directory stored on the handle.
            session_key:         Session key stored on the returned handle.
            existing_sandbox_id: Provider sandbox id to attempt resuming.

        Returns:
            A populated :class:`~tools.sandbox.provider.SandboxHandle`.

        Raises:
            RuntimeError: If the ``opensandbox`` package is not installed.
            SandboxExpiredError: If SDK raises an unrecognised non-expiry error
                during resume (signals the session service to create fresh).
        """
        if SandboxSync is None:
            raise RuntimeError(
                "OpenSandboxProvider requires 'opensandbox' and "
                "'opensandbox-code-interpreter' packages.  "
                "Install them with: "
                "pip install opensandbox>=0.1.7 opensandbox-code-interpreter>=0.1.2"
            )

        config = self._get_config()
        image = _sandbox_image()
        ttl = _session_ttl()

        sandbox = None

        # -- Phase 3: attempt resume when possible --
        if existing_sandbox_id and self._can_resume:
            try:
                sandbox = SandboxSync.resume(
                    existing_sandbox_id,
                    connection_config=config,
                )
                logger.info(
                    "OpenSandboxProvider: resumed sandbox %s", existing_sandbox_id
                )
            except Exception as exc:
                if self._sdk_expiry_exceptions and isinstance(exc, self._sdk_expiry_exceptions):
                    logger.info(
                        "OpenSandboxProvider: sandbox %s expired or unreachable; creating fresh.",
                        existing_sandbox_id,
                    )
                    sandbox = None
                else:
                    raise SandboxExpiredError(
                        f"Unexpected error resuming sandbox {existing_sandbox_id}: {exc}"
                    ) from exc

        if sandbox is None:
            logger.info(
                "OpenSandboxProvider: creating new sandbox (image=%s, ttl=%s, languages=%s)",
                image,
                ttl,
                self.get_supported_languages(),
            )
            sandbox = SandboxSync.create(
                image,
                timeout=ttl,
                resource={"cpu": "1", "memory": "2Gi"},
                env={"PYTHONPATH": _SANDBOX_WORKSPACE},
                connection_config=config,
            )
            logger.info("OpenSandboxProvider: sandbox %s created", sandbox.id)

        return self._setup_sandbox_handle(sandbox, working_dir, session_key)

    def renew_sandbox(self, handle: SandboxHandle, duration: timedelta) -> None:
        """Extend the remote sandbox TTL by *duration* (Phase 3 step 3.3).

        No-op when the SDK lacks the ``renew`` method.  Raises
        :class:`~tools.sandbox.provider.SandboxExpiredError` when the SDK
        signals the sandbox is gone.

        Args:
            handle:   Active sandbox handle.
            duration: How much TTL to add.

        Raises:
            SandboxExpiredError: When the SDK indicates the sandbox is gone,
                or when the handle has no live SDK object (e.g. after a server
                restart — the session service must recreate the sandbox).
        """
        if not self._can_renew:
            return
        sandbox = handle.metadata.get(_META_SANDBOX)
        if sandbox is None:
            raise SandboxExpiredError(
                "Sandbox object not in handle metadata — "
                "sandbox must be recreated (handle reconstructed after restart?)."
            )
        try:
            sandbox.renew(timeout=duration)
        except Exception as exc:
            if self._sdk_expiry_exceptions and isinstance(exc, self._sdk_expiry_exceptions):
                raise SandboxExpiredError(
                    f"Sandbox {handle.sandbox_id} expired during renew: {exc}"
                ) from exc
            raise SandboxExpiredError(
                f"Sandbox {handle.sandbox_id} renew failed: {exc}"
            ) from exc

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
        effective_timeout: int | float = (
            timeout
            if timeout is not None
            else settings.SANDBOX_DEFAULT_TIMEOUT_S
        )

        interpreter = handle.metadata.get(_META_INTERPRETER)

        if interpreter is None:
            return "[Error] OpenSandbox interpreter not initialised for this sandbox."

        context_pools = self._ensure_context_pools(handle)
        if language not in context_pools:
            available = list(context_pools.keys())
            return (
                f"[Error] Language '{language}' is not available in this sandbox. "
                f"Available languages: {available}"
            )

        context_entry = self._acquire_context_entry(
            handle,
            language,
            effective_timeout,
        )
        if context_entry is None:
            return (
                f"[Error] No execution context for language '{language}' became "
                f"available within {effective_timeout}s. "
                "The sandbox is busy; try again or increase "
                "OPENSANDBOX_MAX_CONTEXTS_PER_LANGUAGE."
            )[:effective_limit]
        context = context_entry["context"]

        # Build streaming handlers when the caller wants live stdout lines.
        # Capture the execution id from the init event so a timed-out stream can
        # be interrupted instead of leaving the Jupyter kernel busy indefinitely.
        handlers = None
        execution_id: dict[str, str | None] = {"value": None}
        if on_stdout is not None or effective_timeout > 0:
            try:
                from opensandbox.models.execd_sync import ExecutionHandlersSync

                def _init_cb(msg: object) -> None:
                    execution_id["value"] = (
                        msg.id if hasattr(msg, "id") else str(msg)
                    )

                def _stdout_cb(msg: object) -> None:
                    text: str = msg.text if hasattr(msg, "text") else str(msg)
                    try:
                        on_stdout(text)
                    except Exception:
                        pass  # never let callback errors abort execution

                handlers = ExecutionHandlersSync(
                    on_init=_init_cb,
                    on_stdout=_stdout_cb if on_stdout is not None else None,
                )
            except ImportError:
                pass  # fall back to batch mode if SDK import fails

        try:
            result_queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)
            contextvars_context = copy_context()

            def _run() -> None:
                try:
                    execution_result = interpreter.codes.run(
                        code,
                        context=context,
                        handlers=handlers,
                    )
                    result_queue.put(("ok", execution_result))
                except BaseException as exc:  # noqa: BLE001 - re-raised in caller thread
                    result_queue.put(("error", exc))

            thread = threading.Thread(
                target=lambda: contextvars_context.run(_run),
                name=f"opensandbox-run-{handle.sandbox_id}-{language}",
                daemon=True,
            )
            thread.start()
            thread.join(effective_timeout if effective_timeout > 0 else None)

            if thread.is_alive():
                exec_id = execution_id["value"]
                if exec_id:
                    try:
                        interpreter.codes.interrupt(exec_id)
                    except Exception as interrupt_exc:
                        logger.warning(
                            "OpenSandboxProvider.run_code timeout interrupt failed "
                            "(sandbox_id=%s, execution_id=%s): %s",
                            handle.sandbox_id,
                            exec_id,
                            interrupt_exc,
                        )
                logger.warning(
                    "OpenSandboxProvider.run_code timed out "
                    "(sandbox_id=%s, language=%s, timeout_s=%s, execution_id=%s)",
                    handle.sandbox_id,
                    language,
                    effective_timeout,
                    exec_id,
                )
                return (
                    f"[Error] Code execution timed out after {effective_timeout}s."
                )[:effective_limit]

            status, payload = result_queue.get_nowait()
            if status == "error":
                raise payload
            execution = payload
        except Exception as exc:
            # Phase 3: map SDK expiry signals to SandboxExpiredError so the session
            # service can evict the stale cache entry and recreate on the next turn.
            if self._sdk_expiry_exceptions and isinstance(exc, self._sdk_expiry_exceptions):
                raise SandboxExpiredError(
                    f"Sandbox {handle.sandbox_id} expired during run_code: {exc}"
                ) from exc
            logger.error(
                "OpenSandboxProvider.run_code error (sandbox_id=%s): %s",
                handle.sandbox_id,
                exc,
                exc_info=True,
            )
            return f"[Error] Code execution failed: {exc}"[:effective_limit]
        finally:
            self._release_context_entry(context_entry)

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

        exit_code = getattr(execution, "exit_code", 0)
        if isinstance(exit_code, int) and exit_code != 0 and execution.error is None:
            output_parts.append(f"\n[Error] Non-zero exit code: {exit_code}")

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
            raise SandboxExpiredError(
                f"OpenSandboxProvider: no sandbox object for handle {handle.sandbox_id}"
            )
        remote_path = _workspace_path(filename)
        try:
            sandbox.files.write_file(remote_path, content)
        except Exception as exc:
            if self._sdk_expiry_exceptions and isinstance(exc, self._sdk_expiry_exceptions):
                raise SandboxExpiredError(
                    f"Sandbox {handle.sandbox_id} expired during write_file: {exc}"
                ) from exc
            raise
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
            raise SandboxExpiredError(
                f"OpenSandboxProvider: no sandbox object for handle {handle.sandbox_id}"
            )
        remote_path = _workspace_path(filename)
        try:
            data = sandbox.files.read_bytes(remote_path)
        except Exception as exc:
            if self._sdk_expiry_exceptions and isinstance(exc, self._sdk_expiry_exceptions):
                raise SandboxExpiredError(
                    f"Sandbox {handle.sandbox_id} expired during read_file: {exc}"
                ) from exc
            raise
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
        except ImportError:
            SearchEntry = SimpleNamespace

        try:
            entries = sandbox.files.search(
                SearchEntry(path=_SANDBOX_WORKSPACE, pattern="*")
            )
        except Exception as exc:
            if self._sdk_expiry_exceptions and isinstance(exc, self._sdk_expiry_exceptions):
                raise SandboxExpiredError(
                    f"Sandbox {handle.sandbox_id} expired during list_files: {exc}"
                ) from exc
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

    # ------------------------------------------------------------------
    # Skill activation (Phase 3 step 3.7)
    # ------------------------------------------------------------------

    def ensure_skill(
        self, handle: SandboxHandle, skill: Any, *, retry: bool = False
    ) -> dict[str, Any]:
        """Activate *skill* inside the sandbox using a two-phase approach.

        Phase 1 — files: write all ``SkillFile`` records to
        ``/workspace/.skills/{skill.name}/`` using package-root-relative paths.

        Phase 2 — bootstrap: when ``skill.bootstrap_script_path`` is set, read
        the matching ``SkillFile`` and execute it via :meth:`run_code`.

        Idempotency: if the skill state for the current ``handle.sandbox_id`` is
        already healthy (both phases ok or skipped) and *retry* is ``False``,
        the cached state dict is returned immediately.

        Args:
            handle: Active sandbox handle.
            skill:  ORM ``Skill`` instance.  Must have ``skill_id``, ``name``,
                    ``bootstrap_script_path``, and a ``files`` relationship.
            retry:  When ``True``, re-run even if the skill is already active.

        Returns:
            Phase-status dict keyed as
            ``{"skill_id", "skill_name", "sandbox_id", "files_dir",
              "phases": {"files": str, "bootstrap": str}, "updated_at": str}``.
        """
        from datetime import datetime as _dt

        existing = handle.active_skills.get(skill.name)
        if _healthy_for_sandbox(existing, handle.sandbox_id) and not retry:
            return existing

        files_dir = f"/workspace/.skills/{skill.name}"
        state: dict[str, Any] = {
            "skill_id": skill.skill_id,
            "skill_name": skill.name,
            "sandbox_id": handle.sandbox_id,
            "files_dir": files_dir,
            "phases": {},
            "updated_at": _dt.utcnow().isoformat() + "Z",
        }
        handle.active_skills[skill.name] = state

        # Phase 1: write package files into the sandbox
        try:
            _write_skill_files(self, handle, skill, files_dir)
            state["phases"]["files"] = "ok"
        except Exception as exc:
            state["phases"]["files"] = f"failed: {exc}"
            # Bootstrap depends on files being present — stop here.
            return state

        # Phase 2: run bootstrap script if configured
        if skill.bootstrap_script_path:
            try:
                script = _read_skill_file_text(skill, skill.bootstrap_script_path)
                language = _bootstrap_language_for_path(skill.bootstrap_script_path)
                script = _wrap_bootstrap_script(script, language)
                output = self.run_code(
                    handle,
                    script,
                    language=language,
                    timeout=settings.SANDBOX_SKILL_BOOTSTRAP_TIMEOUT_S,
                )
                if _bootstrap_failed(output):
                    raise RuntimeError(output.strip() or "bootstrap execution failed")
                state["phases"]["bootstrap"] = "ok"
            except Exception as exc:
                state["phases"]["bootstrap"] = f"failed: {exc}"
        else:
            state["phases"]["bootstrap"] = "skipped"

        state["updated_at"] = _dt.utcnow().isoformat() + "Z"
        return state

    def list_active_skills(self, handle: SandboxHandle) -> dict[str, dict[str, Any]]:
        """Return the typed Skill activation state from ``handle.active_skills``."""
        return dict(handle.active_skills)
