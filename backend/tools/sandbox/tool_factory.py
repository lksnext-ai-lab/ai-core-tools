"""
Sandbox tool factory.

``create_sandbox_repl_tool`` produces a language-specific REPL LangChain tool
backed by whatever ``SandboxProvider`` is passed in.  For Python it is a
drop-in replacement for the original ``python_repl`` tool; other languages
produce tools named ``<language>_repl`` (e.g. ``javascript_repl``).

``create_sandbox_repl_tools`` (plural) produces one tool per language listed
in ``provider.get_supported_languages()``, making it the preferred entry point
when the agent builder wants to expose all provider-supported languages.
"""

from __future__ import annotations

from typing import Any

import config as settings
from langchain_core.tools import tool
from langgraph.config import get_stream_writer
from utils.logger import get_logger

from .provider import SandboxProvider, SandboxHandle, SandboxExpiredError
from .builtin_tools import create_sandbox_builtin_tools

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Per-language metadata used to customise each REPL tool's name and docstring.
# ---------------------------------------------------------------------------

_LANGUAGE_META: dict[str, dict[str, str]] = {
    "python": {
        "tool_name": "python_repl",
        "display": "Python",
        "description_extra": (
            "Available libraries: pandas, openpyxl, numpy, os, json, csv, re, datetime."
        ),
    },
    "javascript": {
        "tool_name": "javascript_repl",
        "display": "JavaScript",
        "description_extra": "Runs in a Node.js environment inside the sandbox.",
    },
    "typescript": {
        "tool_name": "typescript_repl",
        "display": "TypeScript",
        "description_extra": "Compiled and executed inside the sandbox (e.g. via ts-node).",
    },
    "bash": {
        "tool_name": "bash_repl",
        "display": "Bash",
        "description_extra": "Standard POSIX shell commands are available.",
    },
    "r": {
        "tool_name": "r_repl",
        "display": "R",
        "description_extra": "Statistical computing with R. Common packages (tidyverse, ggplot2) may be available.",
    },
    "java": {
        "tool_name": "java_repl",
        "display": "Java",
        "description_extra": "Runs inside a JVM context in the sandbox.",
    },
    "go": {
        "tool_name": "go_repl",
        "display": "Go",
        "description_extra": "Compiled and run via the Go toolchain inside the sandbox.",
    },
    "rust": {
        "tool_name": "rust_repl",
        "display": "Rust",
        "description_extra": "Compiled and run via the Rust toolchain inside the sandbox.",
    },
    "csharp": {
        "tool_name": "csharp_repl",
        "display": "C#",
        "description_extra": "Runs inside the .NET runtime in the sandbox.",
    },
    "cpp": {
        "tool_name": "cpp_repl",
        "display": "C++",
        "description_extra": "Compiled and run via a C++ toolchain inside the sandbox.",
    },
    "c": {
        "tool_name": "c_repl",
        "display": "C",
        "description_extra": "Compiled and run via a C toolchain inside the sandbox.",
    },
    "php": {
        "tool_name": "php_repl",
        "display": "PHP",
        "description_extra": "Executed via the PHP CLI inside the sandbox.",
    },
    "ruby": {
        "tool_name": "ruby_repl",
        "display": "Ruby",
        "description_extra": "Executed via the Ruby runtime inside the sandbox.",
    },
    "swift": {
        "tool_name": "swift_repl",
        "display": "Swift",
        "description_extra": "Compiled and run via the Swift toolchain inside the sandbox.",
    },
    "kotlin": {
        "tool_name": "kotlin_repl",
        "display": "Kotlin",
        "description_extra": "Compiled and run via the Kotlin toolchain inside the sandbox.",
    },
}

# Fallback metadata for any language not listed above.
_DEFAULT_LANGUAGE_META: dict[str, str] = {
    "display": "{language}",
    "description_extra": "",
}


def _get_language_meta(language: str) -> dict[str, str]:
    """Return metadata for *language*, falling back to a generic entry."""
    if language in _LANGUAGE_META:
        return _LANGUAGE_META[language]
    return {
        "tool_name": f"{language}_repl",
        "display": language.capitalize(),
        "description_extra": "",
    }


def create_sandbox_repl_tool(
    handle: SandboxHandle,
    provider: SandboxProvider,
    language: str = "python",
    *,
    session_key: str | None = None,
    session_service: Any | None = None,
):
    """Return a language-specific REPL LangChain tool bound to *handle* and *provider*.

    The tool name follows the ``<language>_repl`` convention (e.g.
    ``python_repl``, ``javascript_repl``).  For ``"python"`` this is a
    drop-in replacement for the tool previously created by
    ``python_sandbox_tools.create_python_repl_tool``.

    Args:
        handle:          Active sandbox handle.
        provider:        Resolved ``SandboxProvider`` instance.
        language:        Language identifier (default ``"python"``).
        session_key:     Optional session key; used to evict the stale cache entry
                         on :class:`~tools.sandbox.provider.SandboxExpiredError`.
        session_service: Optional :class:`~services.sandbox_session_service.SandboxSessionService`
                         instance; called to evict the stale entry before re-raising.

    Returns:
        A LangChain tool whose name is ``{language}_repl``.
    """
    # Lazy import (services -> tools would otherwise risk a circular import
    # through this package's __init__.py) — matches the existing lazy-import
    # convention used elsewhere for this exact cross-package dependency
    # (e.g. sandbox_session_service.py's own `from tools.sandbox.factory
    # import _PROVIDER_REGISTRY`).
    from services.sandbox_session_service import SandboxCapacityError

    meta = _get_language_meta(language)
    tool_name: str = meta["tool_name"]
    display: str = meta["display"]
    extra: str = meta["description_extra"]

    base_doc = (
        f"Execute {display} code and return stdout + stderr.\n\n"
        "Use this tool to read, analyse, transform, and create files.\n"
    )
    if extra:
        base_doc += f"\n{extra}\n"
    base_doc += (
        "\nWorkspace layout:\n"
        "- input/: user-provided files.\n"
        "- work/: scratch files, scripts, dependencies, and intermediates.\n"
        "- output/: final user-facing deliverables.\n\n"
        "Read uploads as input/<filename>. Put temporary support files under work/.\n"
        "Save only files the user should receive under output/ and print the\n"
        "output/<filename> path."
    )

    def _get_stream_writer_or_none():
        try:
            return get_stream_writer()
        except Exception:
            return None

    def _emit_code_output(writer: Any | None, stream: str, line: str) -> None:
        """Forward a sandbox output line to the LangGraph custom stream."""
        if writer is None:
            return
        try:
            writer({
                "type": "code_output",
                "tool_name": tool_name,
                "stream": stream,
                "line": line,
            })
        except Exception:
            pass  # never let streaming errors abort execution

    # Per-turn execution budget: mutable counter shared across calls within
    # one agent turn.  LangChain re-creates the tool per turn so this resets
    # automatically between turns.
    _budget: dict[str, int] = {"count": 0}

    # Build the tool function dynamically so that its __name__ matches
    # tool_name (LangChain uses __name__ as the tool name when @tool is applied
    # to a plain function without an explicit name argument).
    def _recreate_stale_handle() -> bool:
        nonlocal handle
        if session_service is None or session_key is None:
            return False
        try:
            session_service.evict(session_key)
            handle = session_service.get_or_create(
                session_key,
                provider,
                handle.working_dir,
            )
            logger.info(
                "Recovered sandbox session %s with new sandbox_id=%s",
                session_key,
                handle.sandbox_id,
            )
            return True
        except Exception as exc:
            logger.warning(
                "Failed to recreate sandbox session %s after expiry: %s",
                session_key,
                exc,
                exc_info=True,
            )
            return False

    def _repl_fn(code: str) -> str:
        nonlocal handle
        _budget["count"] += 1
        max_executions: int = settings.SANDBOX_MAX_EXECUTIONS_PER_TURN
        if _budget["count"] > max_executions:
            return (
                f"[Execution budget exceeded: {max_executions} executions per turn]"
            )
        stream_writer = _get_stream_writer_or_none()
        for attempt in range(2):
            lease_acquired = False
            if session_service is not None and session_key is not None:
                try:
                    lease_acquired = bool(session_service.begin_use(session_key))
                except SandboxExpiredError:
                    if attempt == 0 and _recreate_stale_handle():
                        continue
                    return (
                        "[Error] Sandbox session expired and could not be "
                        "recreated. Please retry the request."
                    )
                except Exception:
                    lease_acquired = False
            try:
                return provider.run_code(
                    handle,
                    code,
                    language=language,
                    on_stdout=lambda line: _emit_code_output(stream_writer, "stdout", line),
                    on_stderr=lambda line: _emit_code_output(stream_writer, "stderr", line),
                )
            except SandboxExpiredError:
                if attempt == 0 and _recreate_stale_handle():
                    continue
                return (
                    "[Error] Sandbox session expired and was reset. "
                    "Please retry the code execution."
                )
            except SandboxCapacityError:
                # Raised by lazy handle materialization (get_or_create) when
                # the process-wide concurrent-sandbox cap is reached. Must
                # not propagate uncaught — that would surface as a raw 500
                # instead of a clean, retryable tool error (see
                # builtin_tools.py's equivalent catch-all for the same class
                # of error on the other sandbox tool family).
                return (
                    "[Error] Sandbox capacity reached, please retry shortly."
                )
            finally:
                if lease_acquired and session_service is not None and session_key is not None:
                    try:
                        session_service.end_use(session_key)
                    except Exception:
                        pass
        return (
            "[Error] Sandbox session expired and was reset. "
            "Please retry the code execution."
        )

    _repl_fn.__name__ = tool_name
    _repl_fn.__doc__ = base_doc

    return tool(_repl_fn)


def create_sandbox_repl_tools(
    handle: SandboxHandle,
    provider: SandboxProvider,
    *,
    session_key: str | None = None,
    session_service: Any | None = None,
) -> list:
    """Return one REPL tool per language supported by *provider*.

    This is the preferred entry point when assembling the tool list for an
    agent — it automatically exposes all languages the provider was configured
    for without requiring the caller to enumerate them manually.

    Args:
        handle:          Active sandbox handle.
        provider:        Resolved ``SandboxProvider`` instance.
        session_key:     Optional session key used for active-use leasing.
        session_service: Optional session service used for active-use leasing.

    Returns:
        A list of LangChain tools, one per language returned by
        ``provider.get_supported_languages()``.
    """
    return [
        create_sandbox_repl_tool(
            handle,
            provider,
            lang,
            session_key=session_key,
            session_service=session_service,
        )
        for lang in provider.get_supported_languages()
    ]
