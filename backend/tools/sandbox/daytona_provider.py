"""
DaytonaProvider — sandbox backend backed by Daytona SaaS.

The provider follows the same ``SandboxProvider`` contract as OpenSandbox:
one sandbox per conversation, files scoped to a provider workspace, explicit
resume attempts, and output truncation.

Configuration (env vars)
------------------------
``DAYTONA_API_KEY``
    Daytona API key. The SDK can also read this directly from the environment.

``DAYTONA_API_URL``
    Daytona API URL. Defaults to the SDK default (currently
    ``https://app.daytona.io/api``).

``DAYTONA_TARGET``
    Daytona target/region.

``DAYTONA_IMAGE`` / ``DAYTONA_SNAPSHOT``
    Optional image or snapshot used when creating a sandbox. If neither is set,
    Daytona creates its default Python sandbox.

``DAYTONA_WORKSPACE``
    Workspace root inside the sandbox. Defaults to ``workspace`` to match
    Daytona's relative-path conventions while still presenting provider callers
    with workspace-relative file paths.

``DAYTONA_SUPPORTED_LANGUAGES``
    Comma-separated language identifiers exposed to the app. Defaults to
    ``python,bash``. Python uses Daytona's stateful code interpreter when
    available; Bash uses Daytona process execution.
"""

from __future__ import annotations

import os
import posixpath
import shlex
from collections.abc import Callable
from datetime import timedelta
from math import ceil
from types import SimpleNamespace
from typing import Any

import config as settings
from utils.logger import get_logger
from .provider import SandboxExpiredError, SandboxHandle, SandboxProvider

logger = get_logger(__name__)

try:
    from daytona import (  # type: ignore[import]
        CreateSandboxFromImageParams,
        CreateSandboxFromSnapshotParams,
        Daytona,
        DaytonaConfig,
        Resources,
    )
    try:
        from daytona import DaytonaError  # type: ignore[import]
    except ImportError:
        DaytonaError = Exception  # type: ignore[assignment]
except ImportError:
    CreateSandboxFromImageParams = None  # type: ignore[assignment]
    CreateSandboxFromSnapshotParams = None  # type: ignore[assignment]
    Daytona = None  # type: ignore[assignment,misc]
    DaytonaConfig = None  # type: ignore[assignment,misc]
    Resources = None  # type: ignore[assignment,misc]
    DaytonaError = Exception  # type: ignore[assignment]


_ENV_API_KEY = "DAYTONA_API_KEY"
_ENV_API_URL = "DAYTONA_API_URL"
_ENV_TARGET = "DAYTONA_TARGET"
_ENV_IMAGE = "DAYTONA_IMAGE"
_ENV_SNAPSHOT = "DAYTONA_SNAPSHOT"
_ENV_LANGUAGE = "DAYTONA_LANGUAGE"
_ENV_WORKSPACE = "DAYTONA_WORKSPACE"
_ENV_SUPPORTED_LANGUAGES = "DAYTONA_SUPPORTED_LANGUAGES"
_ENV_AUTO_STOP_INTERVAL = "DAYTONA_AUTO_STOP_INTERVAL"
_ENV_AUTO_ARCHIVE_INTERVAL = "DAYTONA_AUTO_ARCHIVE_INTERVAL"
_ENV_AUTO_DELETE_INTERVAL = "DAYTONA_AUTO_DELETE_INTERVAL"
_ENV_CPU = "DAYTONA_CPU"
_ENV_MEMORY_GB = "DAYTONA_MEMORY_GB"

_DEFAULT_WORKSPACE = "workspace"

_META_CLIENT = "_daytona_client"
_META_SANDBOX = "_daytona_sandbox"


def _supported_languages() -> list[str]:
    raw = os.getenv(_ENV_SUPPORTED_LANGUAGES, "python,bash")
    seen: set[str] = set()
    result: list[str] = []
    for token in raw.split(","):
        lang = token.strip().lower()
        if lang and lang not in seen:
            seen.add(lang)
            result.append(lang)
    return result or ["python", "bash"]


def _workspace_root() -> str:
    raw = os.getenv(_ENV_WORKSPACE, _DEFAULT_WORKSPACE).strip()
    return raw.strip("/") or _DEFAULT_WORKSPACE


def _workspace_path(filename: str) -> str:
    workspace = _workspace_root()
    normalized = posixpath.normpath(filename)
    if normalized in (workspace, f"/{workspace}"):
        return workspace
    if normalized.startswith(f"{workspace}/"):
        return normalized
    if normalized.startswith(f"/{workspace}/"):
        return normalized[1:]
    if normalized.startswith("/"):
        raise ValueError(f"Remote path must be inside {workspace}: {filename}")
    candidate = posixpath.normpath(f"{workspace}/{normalized}")
    if candidate == workspace or candidate.startswith(f"{workspace}/"):
        return candidate
    raise ValueError(f"Remote path must be inside {workspace}: {filename}")


def _to_workspace_relative(path: str) -> str:
    workspace = _workspace_root().rstrip("/") + "/"
    normalized = posixpath.normpath((path or "").lstrip("/"))
    if normalized.startswith(workspace):
        return normalized[len(workspace):]
    return normalized


def _get_attr(obj: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return default


def _fs(sandbox: Any) -> Any:
    return _get_attr(sandbox, "fs", "file_system", "filesystem")


def _process(sandbox: Any) -> Any:
    return _get_attr(sandbox, "process")


def _code_interpreter(sandbox: Any) -> Any:
    return _get_attr(sandbox, "code_interpreter", "codeInterpreter")


def _call_with_fallbacks(method: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    try:
        return method(*args, **kwargs)
    except TypeError:
        filtered = {k: v for k, v in kwargs.items() if v is not None}
        try:
            return method(*args, **filtered)
        except TypeError:
            return method(*args)


def _truncate(output: str, limit: int) -> str:
    if len(output) <= limit:
        return output
    return output[:limit] + f"\n[Output truncated at {limit} characters]"


def _response_output(response: Any) -> str:
    parts: list[str] = []
    for attr in ("result", "output", "stdout", "text"):
        value = _get_attr(response, attr)
        if value:
            parts.append(str(value))
            break

    stderr = _get_attr(response, "stderr", "error")
    if stderr:
        parts.append(f"\n[stderr]\n{stderr}")

    exit_code = _get_attr(response, "exit_code", "exitCode", default=0)
    if isinstance(exit_code, int) and exit_code != 0 and not stderr:
        parts.append(f"\n[Error] Non-zero exit code: {exit_code}")
    return "\n".join(parts)


def _optional_int_env(name: str) -> int | None:
    raw = os.getenv(name)
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except ValueError:
        logger.warning("DaytonaProvider: ignoring invalid integer env %s=%r", name, raw)
        return None


def _daytona_auto_stop_interval() -> int:
    """Return Daytona auto-stop interval in minutes.

    Daytona's SDK uses minutes for ``auto_stop_interval``. The platform-wide
    idle timeout uses seconds, so default to the nearest whole minute and allow
    an explicit ``DAYTONA_AUTO_STOP_INTERVAL`` override.
    """
    configured = _optional_int_env(_ENV_AUTO_STOP_INTERVAL)
    if configured is not None:
        return max(1, configured)
    try:
        import config as settings  # type: ignore[import]
        idle_seconds = int(getattr(settings, "SANDBOX_IDLE_TIMEOUT_S", 120))
    except Exception:
        idle_seconds = 120
    return max(1, (idle_seconds + 59) // 60)


def _runtime_auto_stop_interval(timeout: int | float) -> int:
    try:
        idle_seconds = int(getattr(settings, "SANDBOX_IDLE_TIMEOUT_S", 120))
    except (TypeError, ValueError):
        idle_seconds = 120
    return max(_daytona_auto_stop_interval(), int(ceil((float(timeout) + idle_seconds) / 60)))


class DaytonaProvider(SandboxProvider):
    """Sandbox provider that executes code inside Daytona SaaS sandboxes."""

    PROVIDER_NAME = "daytona"

    def __init__(self, credentials: dict | None = None) -> None:
        """Initialise the provider.

        Args:
            credentials: Optional per-instance override (``api_key`` /
                ``api_url`` / ``target``) sourced from a ``SandboxService``
                row. When ``None`` (the default), configuration is read
                entirely from the ``DAYTONA_*`` environment variables —
                unchanged behaviour.
        """
        self._client = None
        self._credentials = credentials
        self._capabilities = {"resume": True, "renew": True}

    def get_supported_languages(self) -> list[str]:
        return _supported_languages()

    def _get_client(self) -> Any:
        if Daytona is None:
            raise RuntimeError(
                "DaytonaProvider requires the 'daytona' package. "
                "Install it with: pip install daytona>=0.173.0"
            )
        if self._client is not None:
            return self._client

        creds = self._credentials or {}
        config_kwargs = {
            "api_key": creds.get("api_key") or (os.getenv(_ENV_API_KEY) or None),
            "api_url": creds.get("api_url") or (os.getenv(_ENV_API_URL) or None),
            "target": creds.get("target") or (os.getenv(_ENV_TARGET) or None),
        }
        config_kwargs = {k: v for k, v in config_kwargs.items() if v is not None}
        if DaytonaConfig is not None and config_kwargs:
            self._client = Daytona(DaytonaConfig(**config_kwargs))
        else:
            self._client = Daytona()
        return self._client

    def _create_params(self) -> Any | None:
        image = os.getenv(_ENV_IMAGE)
        snapshot = os.getenv(_ENV_SNAPSHOT)
        language = os.getenv(_ENV_LANGUAGE, "python")
        env_vars = {"PYTHONPATH": _workspace_root()}
        base_kwargs: dict[str, Any] = {
            "language": language,
            "env_vars": env_vars,
            "ephemeral": True,
            "auto_stop_interval": _daytona_auto_stop_interval(),
            "auto_archive_interval": _optional_int_env(_ENV_AUTO_ARCHIVE_INTERVAL),
            "auto_delete_interval": _optional_int_env(_ENV_AUTO_DELETE_INTERVAL),
        }
        base_kwargs = {k: v for k, v in base_kwargs.items() if v is not None}

        cpu = _optional_int_env(_ENV_CPU)
        memory = _optional_int_env(_ENV_MEMORY_GB)
        if Resources is not None and (cpu is not None or memory is not None):
            resource_kwargs = {}
            if cpu is not None:
                resource_kwargs["cpu"] = cpu
            if memory is not None:
                resource_kwargs["memory"] = memory
            base_kwargs["resources"] = Resources(**resource_kwargs)

        if image and CreateSandboxFromImageParams is not None:
            return CreateSandboxFromImageParams(image=image, **base_kwargs)
        if snapshot and CreateSandboxFromSnapshotParams is not None:
            return CreateSandboxFromSnapshotParams(snapshot=snapshot, **base_kwargs)
        if CreateSandboxFromSnapshotParams is not None and base_kwargs:
            return CreateSandboxFromSnapshotParams(**base_kwargs)
        return None

    def _ensure_workspace(self, sandbox: Any) -> None:
        workspace = _workspace_root()
        try:
            fs = _fs(sandbox)
            if fs is not None and hasattr(fs, "create_folder"):
                fs.create_folder(workspace, "755")
                return
        except Exception:
            pass
        try:
            proc = _process(sandbox)
            if proc is not None and hasattr(proc, "exec"):
                proc.exec(f"mkdir -p {shlex.quote(workspace)}")
        except Exception as exc:
            logger.debug("DaytonaProvider: workspace creation skipped: %s", exc)

    def _setup_handle(
        self,
        client: Any,
        sandbox: Any,
        working_dir: str,
        session_key: str | None,
    ) -> SandboxHandle:
        sandbox_id = str(_get_attr(sandbox, "id", "sandbox_id", "sandboxId"))
        self._ensure_workspace(sandbox)
        return SandboxHandle(
            sandbox_id=sandbox_id,
            working_dir=working_dir,
            provider_name=self.PROVIDER_NAME,
            session_key=session_key,
            metadata={
                _META_CLIENT: client,
                _META_SANDBOX: sandbox,
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
        client = self._get_client()
        sandbox = None
        if existing_sandbox_id:
            try:
                sandbox = client.get(existing_sandbox_id)
                if hasattr(client, "start"):
                    try:
                        client.start(sandbox, timeout=settings.SANDBOX_CREATE_TIMEOUT_S)
                    except Exception:
                        pass
                logger.info("DaytonaProvider: resumed sandbox %s", existing_sandbox_id)
            except Exception as exc:
                logger.info(
                    "DaytonaProvider: sandbox %s unavailable; creating fresh: %s",
                    existing_sandbox_id,
                    exc,
                )
                sandbox = None

        if sandbox is None:
            logger.info("DaytonaProvider: creating new sandbox")
            params = self._create_params()
            if params is None:
                sandbox = client.create(timeout=settings.SANDBOX_CREATE_TIMEOUT_S)
            else:
                sandbox = client.create(params, timeout=settings.SANDBOX_CREATE_TIMEOUT_S)
            logger.info("DaytonaProvider: sandbox %s created", _get_attr(sandbox, "id"))

        return self._setup_handle(client, sandbox, working_dir, session_key)

    def renew_sandbox(self, handle: SandboxHandle, duration: timedelta) -> None:
        """Refresh Daytona's idle auto-stop interval for a cached sandbox."""
        sandbox = handle.metadata.get(_META_SANDBOX)
        if sandbox is None:
            raise SandboxExpiredError(
                f"DaytonaProvider: no sandbox object for handle {handle.sandbox_id}"
            )
        try:
            self._set_autostop_interval(sandbox, _daytona_auto_stop_interval())
        except Exception as exc:
            raise SandboxExpiredError(
                f"Daytona sandbox {handle.sandbox_id} renew failed: {exc}"
            ) from exc

    def touch_sandbox(self, handle: SandboxHandle, idle_timeout_s: int) -> None:
        """Refresh Daytona auto-stop and issue lightweight activity."""
        sandbox = handle.metadata.get(_META_SANDBOX)
        if sandbox is None:
            raise SandboxExpiredError(
                f"DaytonaProvider: no sandbox object for handle {handle.sandbox_id}"
            )
        try:
            self._reset_idle_timeout(sandbox)
        except Exception as exc:
            raise SandboxExpiredError(
                f"Daytona sandbox {handle.sandbox_id} touch failed: {exc}"
            ) from exc

    def _set_autostop_interval(
        self,
        sandbox: Any,
        interval_minutes: int,
        *,
        suppress_errors: bool = False,
    ) -> None:
        setter = getattr(sandbox, "set_autostop_interval", None)
        if setter is None:
            return
        try:
            setter(interval_minutes)
        except Exception:
            if suppress_errors:
                logger.debug("DaytonaProvider: auto-stop refresh failed", exc_info=True)
                return
            raise

    def _touch_idle_activity(self, sandbox: Any, *, suppress_errors: bool = False) -> None:
        """Issue a lightweight Toolbox action so Daytona restarts its idle timer.

        Daytona treats ``set_autostop_interval`` as configuration, not as sandbox
        activity. A read-only filesystem call gives the platform an external
        interaction without changing user files. Process execution is kept as a
        fallback for SDK versions without ``fs.list_files``.
        """
        workspace = _workspace_root()
        fs = _fs(sandbox)
        if fs is not None and hasattr(fs, "list_files"):
            try:
                fs.list_files(workspace)
                return
            except Exception:
                if suppress_errors:
                    logger.debug(
                        "DaytonaProvider: idle activity filesystem touch failed",
                        exc_info=True,
                    )
                else:
                    logger.debug(
                        "DaytonaProvider: idle activity filesystem touch failed; "
                        "falling back to process touch",
                        exc_info=True,
                    )

        proc = _process(sandbox)
        if proc is None or not hasattr(proc, "exec"):
            if suppress_errors:
                return
            raise RuntimeError("Daytona sandbox has no toolbox action to refresh idle timer")

        try:
            _call_with_fallbacks(
                proc.exec,
                "true",
                cwd=workspace,
                timeout=1,
            )
        except Exception:
            if suppress_errors:
                logger.debug("DaytonaProvider: idle activity process touch failed", exc_info=True)
                return
            raise

    def _reset_idle_timeout(self, sandbox: Any, *, suppress_errors: bool = False) -> None:
        self._set_autostop_interval(
            sandbox,
            _daytona_auto_stop_interval(),
            suppress_errors=suppress_errors,
        )
        self._touch_idle_activity(sandbox, suppress_errors=suppress_errors)

    def destroy_sandbox(self, handle: SandboxHandle) -> None:
        sandbox = handle.metadata.get(_META_SANDBOX)
        client = handle.metadata.get(_META_CLIENT) or self._client
        if sandbox is None:
            logger.warning(
                "DaytonaProvider.destroy_sandbox: no sandbox object in handle "
                "(sandbox_id=%s) — nothing to clean up",
                handle.sandbox_id,
            )
            return
        try:
            if client is not None and hasattr(client, "delete"):
                client.delete(sandbox)
            elif hasattr(sandbox, "delete"):
                sandbox.delete()
            logger.info("DaytonaProvider: sandbox %s deleted", handle.sandbox_id)
        except Exception as exc:
            logger.warning(
                "DaytonaProvider: error deleting sandbox %s: %s",
                handle.sandbox_id,
                exc,
            )

    def destroy_sandbox_id(self, sandbox_id: str) -> None:
        client = self._get_client()
        try:
            sandbox = client.get(sandbox_id)
        except Exception as exc:
            logger.debug(
                "DaytonaProvider: sandbox %s unavailable during destroy-by-id: %s",
                sandbox_id,
                exc,
            )
            return
        handle = SandboxHandle(
            sandbox_id=sandbox_id,
            working_dir="",
            provider_name=self.PROVIDER_NAME,
            metadata={_META_CLIENT: client, _META_SANDBOX: sandbox},
        )
        self.destroy_sandbox(handle)

    def _run_python(
        self,
        sandbox: Any,
        code: str,
        timeout: int | float,
        on_stdout: Callable[[str], None] | None,
    ) -> Any:
        interpreter = _code_interpreter(sandbox)
        if interpreter is not None and hasattr(interpreter, "run_code"):

            def _stdout(message: Any) -> None:
                if on_stdout is None:
                    return
                text = _get_attr(message, "output", "text", default=str(message))
                try:
                    on_stdout(str(text))
                except Exception:
                    pass

            # Daytona's stateful Python interpreter (interpreter.run_code)
            # has no `cwd` parameter — unlike _run_bash/write_file/read_file/
            # list_files below, which all explicitly operate against
            # _workspace_root(). Confirmed live: the interpreter's own
            # default cwd is the sandbox user's home directory (e.g.
            # /home/daytona), one level ABOVE the workspace root
            # (/home/daytona/workspace). Without this chdir, code writing to
            # a relative path like "output/foo.csv" (the convention every
            # agent is instructed to use) lands outside the workspace root
            # entirely and is never seen by list_files()/read_file() —
            # the file exists but is never synced back to the user.
            # Idempotent and cheap to repeat every call rather than relying
            # on interpreter state (e.g. a fresh context via `context=`).
            workspace = _workspace_root()
            code = (
                f"import os as __mattin_os\n"
                f"__mattin_os.makedirs({workspace!r}, exist_ok=True)\n"
                f"__mattin_os.chdir({workspace!r})\n"
                f"del __mattin_os\n"
            ) + code

            return _call_with_fallbacks(
                interpreter.run_code,
                code,
                on_stdout=_stdout if on_stdout is not None else None,
                timeout=timeout,
            )

        proc = _process(sandbox)
        if proc is None or not hasattr(proc, "code_run"):
            raise RuntimeError("Daytona sandbox has no code interpreter or process.code_run")
        return _call_with_fallbacks(proc.code_run, code, timeout=timeout)

    def _run_bash(self, sandbox: Any, code: str, timeout: int | float) -> Any:
        proc = _process(sandbox)
        if proc is None or not hasattr(proc, "exec"):
            raise RuntimeError("Daytona sandbox has no process.exec service")
        command = f"bash -lc {shlex.quote(code)}"
        return _call_with_fallbacks(
            proc.exec,
            command,
            cwd=_workspace_root(),
            timeout=timeout,
        )

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
                f"DaytonaProvider: no sandbox object for handle {handle.sandbox_id}"
            )

        try:
            self._set_autostop_interval(
                sandbox,
                _runtime_auto_stop_interval(effective_timeout),
            )
            try:
                if language == "python":
                    response = self._run_python(sandbox, code, effective_timeout, on_stdout)
                elif language == "bash":
                    response = self._run_bash(sandbox, code, effective_timeout)
                else:
                    proc = _process(sandbox)
                    if proc is None or not hasattr(proc, "code_run"):
                        return (
                            f"[Error] Language '{language}' is not supported by DaytonaProvider. "
                            "Supported persistent execution: python; command execution: bash."
                        )[:effective_limit]
                    response = _call_with_fallbacks(proc.code_run, code, timeout=effective_timeout)
            finally:
                self._reset_idle_timeout(sandbox, suppress_errors=True)
        except Exception as exc:
            logger.error(
                "DaytonaProvider.run_code error (sandbox_id=%s): %s",
                handle.sandbox_id,
                exc,
                exc_info=True,
            )
            return f"[Error] Code execution failed: {exc}"[:effective_limit]

        output = _response_output(response)
        if on_stderr is not None and "[stderr]" in output:
            stderr = output.split("[stderr]", 1)[1].strip()
            for line in stderr.splitlines():
                try:
                    on_stderr(line)
                except Exception:
                    pass
        return _truncate(output, effective_limit)

    def write_file(self, handle: SandboxHandle, filename: str, content: bytes) -> None:
        sandbox = handle.metadata.get(_META_SANDBOX)
        if sandbox is None:
            raise SandboxExpiredError(
                f"DaytonaProvider: no sandbox object for handle {handle.sandbox_id}"
            )
        self._reset_idle_timeout(sandbox)
        remote_path = _workspace_path(filename)
        parent = posixpath.dirname(remote_path)
        try:
            if parent:
                try:
                    proc = _process(sandbox)
                    if proc is not None and hasattr(proc, "exec"):
                        proc.exec(f"mkdir -p {shlex.quote(parent)}")
                except Exception:
                    pass
            fs = _fs(sandbox)
            if fs is None or not hasattr(fs, "upload_file"):
                raise RuntimeError("Daytona sandbox has no fs.upload_file service")
            fs.upload_file(content, remote_path)
        finally:
            self._reset_idle_timeout(sandbox, suppress_errors=True)
        logger.debug(
            "DaytonaProvider.write_file: wrote %d bytes to %s (sandbox=%s)",
            len(content),
            remote_path,
            handle.sandbox_id,
        )

    @staticmethod
    def _raise_on_process_failure(response: Any, action: str) -> None:
        exit_code = _get_attr(response, "exit_code", "exitCode", default=0)
        if isinstance(exit_code, int) and exit_code != 0:
            output = _response_output(response).strip()
            detail = f": {output}" if output else ""
            raise RuntimeError(f"Failed to {action}{detail}")

    def read_file(self, handle: SandboxHandle, filename: str) -> bytes:
        sandbox = handle.metadata.get(_META_SANDBOX)
        if sandbox is None:
            raise SandboxExpiredError(
                f"DaytonaProvider: no sandbox object for handle {handle.sandbox_id}"
            )
        self._reset_idle_timeout(sandbox)
        try:
            fs = _fs(sandbox)
            if fs is None or not hasattr(fs, "download_file"):
                raise RuntimeError("Daytona sandbox has no fs.download_file service")
            data = fs.download_file(_workspace_path(filename))
        finally:
            self._reset_idle_timeout(sandbox, suppress_errors=True)
        if isinstance(data, str):
            return data.encode("utf-8")
        return bytes(data)

    def list_files(self, handle: SandboxHandle) -> list[str]:
        sandbox = handle.metadata.get(_META_SANDBOX)
        if sandbox is None:
            raise SandboxExpiredError(
                f"DaytonaProvider: no sandbox object for handle {handle.sandbox_id}"
            )
        fs = _fs(sandbox)
        if fs is None:
            return []

        result: list[str] = []
        try:
            self._reset_idle_timeout(sandbox)
            if hasattr(fs, "search_files"):
                found = fs.search_files(_workspace_root(), "*")
                files = _get_attr(found, "files", default=found)
                for path in files or []:
                    rel = _to_workspace_relative(str(path))
                    if rel:
                        result.append(rel)
                return sorted(set(result))
        except Exception as exc:
            logger.debug("DaytonaProvider.list_files: search_files failed: %s", exc)
        finally:
            self._reset_idle_timeout(sandbox, suppress_errors=True)

        def _walk(path: str) -> None:
            try:
                entries = fs.list_files(path)
            except Exception:
                return
            for entry in entries or []:
                name = str(_get_attr(entry, "name", "path", default=""))
                child_path = name if name.startswith(path) else posixpath.join(path, name)
                rel = _to_workspace_relative(child_path)
                if bool(_get_attr(entry, "is_dir", "isDir", default=False)):
                    _walk(child_path)
                elif rel:
                    result.append(rel)

        if hasattr(fs, "list_files"):
            self._reset_idle_timeout(sandbox)
            try:
                _walk(_workspace_root())
            finally:
                self._reset_idle_timeout(sandbox, suppress_errors=True)
        return sorted(set(result))
