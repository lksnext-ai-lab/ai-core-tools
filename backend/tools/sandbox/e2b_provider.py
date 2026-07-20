"""
E2BProvider — sandbox backend backed by E2B Cloud.

Uses the E2B Code Interpreter SDK when available so Python execution behaves
like OpenSandbox/Daytona: one cloud sandbox per conversation, persistent code
context, workspace-scoped files, stdout/stderr callbacks, and output
truncation.

Configuration (env vars)
------------------------
``E2B_API_KEY``
    E2B API key. The SDK also reads this directly from the environment.

``E2B_TEMPLATE``
    Optional E2B sandbox template name or ID. Defaults to the SDK default.

``E2B_WORKSPACE``
    Workspace root inside the sandbox. Defaults to ``/home/user/workspace``.

``E2B_SUPPORTED_LANGUAGES``
    Comma-separated language identifiers exposed to the app. Defaults to
    ``python,javascript,bash``. Python and JavaScript use E2B's stateful code
    interpreter; Bash uses command execution.
"""

from __future__ import annotations

import os
import posixpath
import shlex
from collections.abc import Callable
from datetime import timedelta
from math import ceil
from typing import Any

import config as settings
from utils.logger import get_logger
from .provider import SandboxExpiredError, SandboxHandle, SandboxProvider

logger = get_logger(__name__)

try:
    from e2b_code_interpreter import Sandbox as E2BSandbox  # type: ignore[import]
except ImportError:
    try:
        from e2b import Sandbox as E2BSandbox  # type: ignore[import]
    except ImportError:
        E2BSandbox = None  # type: ignore[assignment,misc]


_ENV_TEMPLATE = "E2B_TEMPLATE"
_ENV_WORKSPACE = "E2B_WORKSPACE"
_ENV_SUPPORTED_LANGUAGES = "E2B_SUPPORTED_LANGUAGES"
_ENV_ALLOW_INTERNET = "E2B_ALLOW_INTERNET_ACCESS"
_ENV_SECURE = "E2B_SECURE"

_DEFAULT_WORKSPACE = "/home/user/workspace"

_META_SANDBOX = "_e2b_sandbox"
_META_CONTEXTS = "_e2b_contexts"


def _supported_languages() -> list[str]:
    raw = os.getenv(_ENV_SUPPORTED_LANGUAGES, "python,javascript,bash")
    seen: set[str] = set()
    result: list[str] = []
    for token in raw.split(","):
        lang = token.strip().lower()
        if lang and lang not in seen:
            seen.add(lang)
            result.append(lang)
    return result or ["python", "javascript", "bash"]


def _workspace_root() -> str:
    raw = os.getenv(_ENV_WORKSPACE, _DEFAULT_WORKSPACE).strip()
    if not raw:
        return _DEFAULT_WORKSPACE
    return posixpath.normpath(raw if raw.startswith("/") else f"/home/user/{raw}")


def _workspace_path(filename: str) -> str:
    workspace = _workspace_root()
    normalized = posixpath.normpath(filename)
    if normalized in (workspace, workspace.lstrip("/")):
        return workspace
    if normalized.startswith(f"{workspace}/"):
        return normalized
    if normalized.startswith(f"{workspace.lstrip('/')}/"):
        return f"/{normalized}"
    if normalized.startswith("/"):
        raise ValueError(f"Remote path must be inside {workspace}: {filename}")
    candidate = posixpath.normpath(f"{workspace}/{normalized}")
    if candidate == workspace or candidate.startswith(f"{workspace}/"):
        return candidate
    raise ValueError(f"Remote path must be inside {workspace}: {filename}")


def _to_workspace_relative(path: str) -> str:
    workspace = _workspace_root().rstrip("/") + "/"
    normalized = posixpath.normpath(path or "")
    if normalized.startswith(workspace):
        return normalized[len(workspace):]
    return normalized.lstrip("/")


def _get_attr(obj: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return default


def _call_with_fallbacks(method: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    try:
        return method(*args, **kwargs)
    except TypeError:
        filtered = {k: v for k, v in kwargs.items() if v is not None}
        try:
            return method(*args, **filtered)
        except TypeError:
            return method(*args)


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _idle_timeout_s() -> int:
    try:
        return max(1, int(getattr(settings, "SANDBOX_IDLE_TIMEOUT_S", 120)))
    except (TypeError, ValueError):
        return 120


def _runtime_timeout_s(timeout: int | float) -> int:
    return max(_idle_timeout_s(), int(ceil(float(timeout))) + _idle_timeout_s())


def _truncate(output: str, limit: int) -> str:
    if len(output) <= limit:
        return output
    return output[:limit] + f"\n[Output truncated at {limit} characters]"


def _message_text(message: Any) -> str:
    return str(_get_attr(message, "text", "line", "output", default=message))


def _execution_output(execution: Any) -> str:
    parts: list[str] = []

    text = _get_attr(execution, "text")
    if text:
        parts.append(str(text))

    results = _get_attr(execution, "results", "result")
    if results and not text:
        if isinstance(results, list):
            parts.extend(str(_get_attr(r, "text", "value", default=r)) for r in results)
        else:
            parts.append(str(_get_attr(results, "text", "value", default=results)))

    logs = _get_attr(execution, "logs")
    stdout = _get_attr(logs, "stdout", default=None) if logs is not None else None
    if stdout and not parts:
        parts.extend(_message_text(line) for line in stdout)

    error = _get_attr(execution, "error")
    if error:
        name = _get_attr(error, "name", default="Error")
        value = _get_attr(error, "value", "message", default=error)
        parts.append(f"\n[Error] {name}: {value}")

    stderr = _get_attr(logs, "stderr", default=None) if logs is not None else None
    if stderr:
        stderr_text = "\n".join(_message_text(line) for line in stderr)
        if stderr_text.strip():
            parts.append(f"\n[stderr]\n{stderr_text}")

    exit_code = _get_attr(execution, "exit_code", "exitCode", default=0)
    if isinstance(exit_code, int) and exit_code != 0 and not error:
        parts.append(f"\n[Error] Non-zero exit code: {exit_code}")

    return "\n".join(part for part in parts if part)


def _command_output(result: Any) -> str:
    parts: list[str] = []
    stdout = _get_attr(result, "stdout", "output", "text")
    stderr = _get_attr(result, "stderr", "error")
    if stdout:
        parts.append(str(stdout))
    if stderr:
        parts.append(f"\n[stderr]\n{stderr}")
    exit_code = _get_attr(result, "exit_code", "exitCode", default=0)
    if isinstance(exit_code, int) and exit_code != 0 and not stderr:
        parts.append(f"\n[Error] Non-zero exit code: {exit_code}")
    return "\n".join(parts)


def _is_expiry_error(exc: Exception) -> bool:
    """Return True for E2B errors that mean the remote sandbox is gone."""
    if isinstance(exc, SandboxExpiredError):
        return True
    exc_name = exc.__class__.__name__.lower()
    message = str(exc).lower()
    return (
        ("sandbox" in message and "not found" in message)
        or "sandboxnotfound" in exc_name
        or "sandbox_not_found" in exc_name
    )


class E2BProvider(SandboxProvider):
    """Sandbox provider that executes code inside E2B Cloud sandboxes."""

    PROVIDER_NAME = "e2b"

    def __init__(self, credentials: dict | None = None) -> None:
        """Initialise the provider.

        Args:
            credentials: Optional per-instance override (``api_key`` /
                ``template``) sourced from a ``SandboxService`` row. When
                ``None`` (the default), configuration is read entirely from
                the ``E2B_*`` environment variables — unchanged behaviour.
        """
        self._credentials = credentials
        self._capabilities = {"resume": True, "renew": True}

    def get_supported_languages(self) -> list[str]:
        return _supported_languages()

    def _ensure_sdk(self) -> Any:
        if E2BSandbox is None:
            raise RuntimeError(
                "E2BProvider requires 'e2b-code-interpreter'. "
                "Install it with: pip install e2b-code-interpreter>=2.5.0"
            )
        return E2BSandbox

    def _ensure_workspace(self, sandbox: Any) -> None:
        try:
            sandbox.commands.run(
                f"mkdir -p {shlex.quote(_workspace_root())}",
                timeout=settings.SANDBOX_DEFAULT_TIMEOUT_S,
                request_timeout=settings.SANDBOX_CREATE_TIMEOUT_S,
            )
        except Exception as exc:
            logger.debug("E2BProvider: workspace creation skipped: %s", exc)

    def _setup_handle(
        self,
        sandbox: Any,
        working_dir: str,
        session_key: str | None,
    ) -> SandboxHandle:
        sandbox_id = str(_get_attr(sandbox, "sandbox_id", "id", "sandboxId"))
        self._ensure_workspace(sandbox)
        return SandboxHandle(
            sandbox_id=sandbox_id,
            working_dir=working_dir,
            provider_name=self.PROVIDER_NAME,
            session_key=session_key,
            metadata={
                _META_SANDBOX: sandbox,
                _META_CONTEXTS: {},
                "provider_capabilities": self._capabilities,
            },
        )

    def create_sandbox(
        self,
        working_dir: str,
        *,
        session_key: str | None = None,
        existing_sandbox_id: str | None = None,
    ) -> SandboxHandle:
        sdk = self._ensure_sdk()
        sandbox = None
        timeout_s = _idle_timeout_s()
        request_timeout_s = settings.SANDBOX_CREATE_TIMEOUT_S
        api_key = (self._credentials or {}).get("api_key") or None

        if existing_sandbox_id:
            try:
                sandbox = _call_with_fallbacks(
                    sdk.connect,
                    existing_sandbox_id,
                    timeout=timeout_s,
                    request_timeout=request_timeout_s,
                    api_key=api_key,
                )
                logger.info("E2BProvider: resumed sandbox %s", existing_sandbox_id)
            except Exception as exc:
                logger.info(
                    "E2BProvider: sandbox %s unavailable; creating fresh: %s",
                    existing_sandbox_id,
                    exc,
                )
                sandbox = None

        if sandbox is None:
            template = (self._credentials or {}).get("template") or (os.getenv(_ENV_TEMPLATE) or None)
            metadata = {"provider": self.PROVIDER_NAME}
            if session_key:
                metadata["session_key"] = session_key
            sandbox = _call_with_fallbacks(
                sdk.create,
                template=template,
                timeout=timeout_s,
                metadata=metadata,
                envs={"PYTHONPATH": _workspace_root()},
                secure=_bool_env(_ENV_SECURE, True),
                allow_internet_access=_bool_env(_ENV_ALLOW_INTERNET, True),
                request_timeout=request_timeout_s,
                api_key=api_key,
            )
            logger.info("E2BProvider: sandbox %s created", _get_attr(sandbox, "sandbox_id", "id"))

        return self._setup_handle(sandbox, working_dir, session_key)

    def renew_sandbox(self, handle: SandboxHandle, duration: timedelta) -> None:
        sandbox = handle.metadata.get(_META_SANDBOX)
        if sandbox is None:
            raise SandboxExpiredError(
                f"E2BProvider: no sandbox object for handle {handle.sandbox_id}"
            )
        try:
            self._set_sandbox_timeout(sandbox, _idle_timeout_s())
        except Exception as exc:
            raise SandboxExpiredError(
                f"E2B sandbox {handle.sandbox_id} renew failed: {exc}"
            ) from exc

    def touch_sandbox(self, handle: SandboxHandle, idle_timeout_s: int) -> None:
        """Refresh E2B timeout to the service-managed idle window."""
        sandbox = handle.metadata.get(_META_SANDBOX)
        if sandbox is None:
            raise SandboxExpiredError(
                f"E2BProvider: no sandbox object for handle {handle.sandbox_id}"
            )
        try:
            self._set_sandbox_timeout(sandbox, max(1, int(idle_timeout_s)))
        except Exception as exc:
            raise SandboxExpiredError(
                f"E2B sandbox {handle.sandbox_id} touch failed: {exc}"
            ) from exc

    def _set_sandbox_timeout(
        self,
        sandbox: Any,
        timeout_s: int,
        *,
        suppress_errors: bool = False,
    ) -> None:
        if not hasattr(sandbox, "set_timeout"):
            return
        try:
            sandbox.set_timeout(timeout_s)
        except Exception:
            if suppress_errors:
                logger.debug("E2BProvider: sandbox timeout refresh failed", exc_info=True)
                return
            raise

    def _reset_idle_timeout(self, sandbox: Any, *, suppress_errors: bool = False) -> None:
        self._set_sandbox_timeout(
            sandbox,
            _idle_timeout_s(),
            suppress_errors=suppress_errors,
        )

    def destroy_sandbox(self, handle: SandboxHandle) -> None:
        sandbox = handle.metadata.get(_META_SANDBOX)
        try:
            if sandbox is not None and hasattr(sandbox, "kill"):
                sandbox.kill()
            elif E2BSandbox is not None and hasattr(E2BSandbox, "kill"):
                E2BSandbox.kill(handle.sandbox_id)
            logger.info("E2BProvider: sandbox %s killed", handle.sandbox_id)
        except Exception as exc:
            logger.warning(
                "E2BProvider: error killing sandbox %s: %s",
                handle.sandbox_id,
                exc,
            )

    def destroy_sandbox_id(self, sandbox_id: str) -> None:
        sdk = self._ensure_sdk()
        try:
            if hasattr(sdk, "kill"):
                sdk.kill(sandbox_id)
                logger.info("E2BProvider: sandbox %s killed by id", sandbox_id)
                return
        except Exception as exc:
            logger.debug("E2BProvider: static kill failed for %s: %s", sandbox_id, exc)
        try:
            sandbox = _call_with_fallbacks(
                sdk.connect,
                sandbox_id,
                timeout=_idle_timeout_s(),
                request_timeout=settings.SANDBOX_CREATE_TIMEOUT_S,
            )
        except Exception as exc:
            logger.debug(
                "E2BProvider: sandbox %s unavailable during destroy-by-id: %s",
                sandbox_id,
                exc,
            )
            return
        self.destroy_sandbox(
            SandboxHandle(
                sandbox_id=sandbox_id,
                working_dir="",
                provider_name=self.PROVIDER_NAME,
                metadata={_META_SANDBOX: sandbox},
            )
        )

    def _run_bash(
        self,
        sandbox: Any,
        code: str,
        timeout: int | float,
        on_stdout: Callable[[str], None] | None,
        on_stderr: Callable[[str], None] | None,
    ) -> Any:
        return sandbox.commands.run(
            f"bash -lc {shlex.quote(code)}",
            cwd=_workspace_root(),
            on_stdout=on_stdout,
            on_stderr=on_stderr,
            timeout=timeout,
            request_timeout=timeout,
        )

    def _get_code_context(
        self,
        handle: SandboxHandle,
        sandbox: Any,
        language: str,
    ) -> Any | None:
        """Return a stateful E2B code context rooted at the workspace.

        E2B's default code context starts in ``/home/user``.  Without an
        explicit context, relative outputs are created outside the configured
        workspace and therefore never show up in the file sync path.
        """
        contexts = handle.metadata.setdefault(_META_CONTEXTS, {})
        if not isinstance(contexts, dict):
            contexts = {}
            handle.metadata[_META_CONTEXTS] = contexts

        if language in contexts:
            return contexts[language]

        create_context = getattr(sandbox, "create_code_context", None)
        if create_context is None:
            return None

        workspace = _workspace_root()
        try:
            context = create_context(
                cwd=workspace,
                language=language,
                request_timeout=settings.SANDBOX_CREATE_TIMEOUT_S,
            )
        except TypeError:
            try:
                context = create_context(cwd=workspace, language=language)
            except TypeError:
                context = create_context(cwd=workspace)
        contexts[language] = context
        return context

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
        effective_limit = (
            max_output_chars
            if max_output_chars is not None
            else settings.SANDBOX_MAX_OUTPUT_CHARS
        )
        effective_timeout = (
            timeout
            if timeout is not None
            else settings.SANDBOX_DEFAULT_TIMEOUT_S
        )
        language = language.lower()
        if language not in self.get_supported_languages():
            return (
                f"[Error] Language '{language}' is not available in this sandbox. "
                f"Available languages: {self.get_supported_languages()}"
            )[:effective_limit]

        sandbox = handle.metadata.get(_META_SANDBOX)
        if sandbox is None:
            raise SandboxExpiredError(
                f"E2BProvider: no sandbox object for handle {handle.sandbox_id}"
            )

        try:
            self._set_sandbox_timeout(sandbox, _runtime_timeout_s(effective_timeout))
            if language == "bash":
                try:
                    result = self._run_bash(
                        sandbox,
                        code,
                        effective_timeout,
                        on_stdout,
                        on_stderr,
                    )
                finally:
                    self._reset_idle_timeout(sandbox, suppress_errors=True)
                return _truncate(_command_output(result), effective_limit)

            if not hasattr(sandbox, "run_code"):
                self._reset_idle_timeout(sandbox, suppress_errors=True)
                return (
                    "[Error] E2B Code Interpreter SDK is required for non-bash "
                    "language execution."
                )[:effective_limit]

            def _stdout_cb(msg: Any) -> None:
                if on_stdout is None:
                    return
                try:
                    on_stdout(_message_text(msg))
                except Exception:
                    pass

            def _stderr_cb(msg: Any) -> None:
                if on_stderr is None:
                    return
                try:
                    on_stderr(_message_text(msg))
                except Exception:
                    pass

            context = self._get_code_context(handle, sandbox, language)
            run_kwargs = {
                "on_stdout": _stdout_cb if on_stdout else None,
                "on_stderr": _stderr_cb if on_stderr else None,
                "timeout": effective_timeout,
                "request_timeout": effective_timeout,
            }
            if context is not None:
                run_kwargs["context"] = context
            else:
                run_kwargs["language"] = language

            try:
                execution = sandbox.run_code(code, **run_kwargs)
            finally:
                self._reset_idle_timeout(sandbox, suppress_errors=True)
        except Exception as exc:
            if _is_expiry_error(exc):
                raise SandboxExpiredError(
                    f"E2B sandbox {handle.sandbox_id} expired during run_code: {exc}"
                ) from exc
            logger.error(
                "E2BProvider.run_code error (sandbox_id=%s): %s",
                handle.sandbox_id,
                exc,
                exc_info=True,
            )
            return f"[Error] Code execution failed: {exc}"[:effective_limit]

        return _truncate(_execution_output(execution), effective_limit)

    def write_file(self, handle: SandboxHandle, filename: str, content: bytes) -> None:
        sandbox = handle.metadata.get(_META_SANDBOX)
        if sandbox is None:
            raise SandboxExpiredError(
                f"E2BProvider: no sandbox object for handle {handle.sandbox_id}"
            )
        self._reset_idle_timeout(sandbox)
        try:
            sandbox.files.write(
                _workspace_path(filename),
                content,
                request_timeout=settings.SANDBOX_DEFAULT_TIMEOUT_S,
            )
        finally:
            self._reset_idle_timeout(sandbox, suppress_errors=True)

    def read_file(self, handle: SandboxHandle, filename: str) -> bytes:
        sandbox = handle.metadata.get(_META_SANDBOX)
        if sandbox is None:
            raise SandboxExpiredError(
                f"E2BProvider: no sandbox object for handle {handle.sandbox_id}"
            )
        self._reset_idle_timeout(sandbox)
        try:
            data = sandbox.files.read(
                _workspace_path(filename),
                format="bytes",
                request_timeout=settings.SANDBOX_DEFAULT_TIMEOUT_S,
            )
        finally:
            self._reset_idle_timeout(sandbox, suppress_errors=True)
        return bytes(data)

    def list_files(self, handle: SandboxHandle) -> list[str]:
        sandbox = handle.metadata.get(_META_SANDBOX)
        if sandbox is None:
            raise SandboxExpiredError(
                f"E2BProvider: no sandbox object for handle {handle.sandbox_id}"
            )
        result: list[str] = []
        try:
            self._reset_idle_timeout(sandbox)
            entries = sandbox.files.list(
                _workspace_root(),
                depth=20,
                request_timeout=settings.SANDBOX_DEFAULT_TIMEOUT_S,
            )
        except Exception as exc:
            logger.warning(
                "E2BProvider.list_files: list failed (sandbox=%s): %s",
                handle.sandbox_id,
                exc,
            )
            return []
        finally:
            self._reset_idle_timeout(sandbox, suppress_errors=True)

        for entry in entries or []:
            path = str(_get_attr(entry, "path", default=""))
            if not path:
                name = str(_get_attr(entry, "name", default=""))
                path = posixpath.join(_workspace_root(), name)
            rel = _to_workspace_relative(path)
            entry_type = str(_get_attr(entry, "type", default="")).lower()
            is_dir = bool(_get_attr(entry, "is_dir", "isDir", default=False))
            if not rel or rel == ".":
                continue
            if is_dir or entry_type == "dir":
                continue
            result.append(rel)
        return sorted(set(result))
