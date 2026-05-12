"""
Sandbox tool factory.

``create_sandbox_repl_tool`` produces a language-specific REPL LangChain tool
backed by whatever ``SandboxProvider`` is passed in.  For Python it is a
drop-in replacement for the original ``python_repl`` tool; other languages
produce tools named ``<language>_repl`` (e.g. ``javascript_repl``).

``create_sandbox_repl_tools`` (plural) produces one tool per language listed
in ``provider.get_supported_languages()``, making it the preferred entry point
when the agent builder wants to expose all provider-supported languages.

``create_sandbox_skill_tools`` (IT-3) returns recovery/debug tools for sandbox
Skill activation. Normal Skill usage should go through ``load_skill``, which
loads instructions and prepares the sandbox in one step.
"""

from __future__ import annotations

from typing import Any

import config as settings
from langchain_core.tools import tool
from langgraph.config import get_stream_writer

from .provider import SandboxProvider, SandboxHandle, SandboxExpiredError

# ---------------------------------------------------------------------------
# Per-language metadata used to customise each REPL tool's name and docstring.
# ---------------------------------------------------------------------------

_LANGUAGE_META: dict[str, dict[str, str]] = {
    "python": {
        "tool_name": "python_repl",
        "display": "Python",
        "description_extra": (
            "Available libraries: pandas, openpyxl, numpy, os, json, csv, re, datetime.\n\n"
            "If a task requires a Skill, use ``load_skill`` first. That tool\n"
            "loads the Skill instructions and prepares any bundled sandbox files."
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
        "\nFiles uploaded by the user are in the current working directory — reference\n"
        "them by filename only (e.g. 'report.xlsx', not a full path).\n\n"
        "Save output files to the current working directory and print the filename\n"
        "so the user knows what to download."
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
    def _repl_fn(code: str) -> str:
        _budget["count"] += 1
        max_executions: int = settings.SANDBOX_MAX_EXECUTIONS_PER_TURN
        if _budget["count"] > max_executions:
            return (
                f"[Execution budget exceeded: {max_executions} executions per turn]"
            )
        stream_writer = _get_stream_writer_or_none()
        try:
            return provider.run_code(
                handle,
                code,
                language=language,
                on_stdout=lambda line: _emit_code_output(stream_writer, "stdout", line),
                on_stderr=lambda line: _emit_code_output(stream_writer, "stderr", line),
            )
        except SandboxExpiredError:
            # Evict the stale cache entry so the next agent turn creates a fresh
            # sandbox.  We re-raise so the LLM receives an error explaining that
            # the sandbox was reset and it should retry.
            if session_service is not None and session_key is not None:
                try:
                    session_service.evict(session_key)
                except Exception:
                    pass  # evict is best-effort
            raise

    _repl_fn.__name__ = tool_name
    _repl_fn.__doc__ = base_doc

    return tool(_repl_fn)


def create_sandbox_repl_tools(
    handle: SandboxHandle,
    provider: SandboxProvider,
) -> list:
    """Return one REPL tool per language supported by *provider*.

    This is the preferred entry point when assembling the tool list for an
    agent — it automatically exposes all languages the provider was configured
    for without requiring the caller to enumerate them manually.

    Args:
        handle:   Active sandbox handle.
        provider: Resolved ``SandboxProvider`` instance.

    Returns:
        A list of LangChain tools, one per language returned by
        ``provider.get_supported_languages()``.
    """
    return [
        create_sandbox_repl_tool(handle, provider, lang)
        for lang in provider.get_supported_languages()
    ]


def create_sandbox_skill_tools(
    handle: SandboxHandle,
    provider: SandboxProvider,
    skill_associations: list,
) -> list:
    """Return ``activate_sandbox_skill`` and ``list_active_sandbox_skills`` tools.

    These tools are for explicit recovery/debug activation. The normal path is
    ``load_skill``, which loads instructions and prepares bundled sandbox files.
    Only Skills with ``runtime == "python-sandbox"`` that are attached to the
    agent (via *skill_associations*) may be activated here. Skills without a
    runtime tag are prompt-only and do not appear in the activation map.

    Args:
        handle:            Active sandbox handle.
        provider:          Resolved sandbox provider.
        skill_associations: ``agent.skill_associations`` — the agent's attached skills.

    Returns:
        A list of two LangChain tools, or an empty list when no runtime skills
        are attached to the agent.
    """
    allowed_skills: dict = {
        assoc.skill.name.lower().strip(): assoc.skill
        for assoc in skill_associations
        if assoc.skill and assoc.skill.runtime == "python-sandbox"
    }

    if not allowed_skills:
        return []

    available_names = ", ".join(sorted(allowed_skills))

    @tool
    def activate_sandbox_skill(skill_name: str) -> str:
        """Retry sandbox activation for one attached Skill.

        Use this only when ``load_skill`` already loaded the Skill but sandbox
        setup needs an explicit retry, or when a user/admin explicitly asks to
        repair Skill activation. Normal task execution should call
        ``load_skill`` instead. Activation is idempotent — calling it again for
        an already-active Skill is a no-op.

        Args:
            skill_name: Name of the skill to activate (case-insensitive).

        Returns:
            Confirmation message, or an error if the skill is not available.
        """
        key = skill_name.lower().strip()
        skill = allowed_skills.get(key)
        if not skill:
            return (
                f"Skill '{skill_name}' is not available for sandbox activation. "
                f"Available runtime skills: {available_names}"
            )
        try:
            provider.ensure_skill(handle, skill)
        except NotImplementedError:
            return (
                f"Skill activation is not supported by the current sandbox provider "
                f"('{handle.provider_name}'). The skill may still be usable if its "
                f"dependencies are already installed."
            )
        return f"Skill '{skill.name}' is active in the sandbox."

    # Inject the available skill names into the tool description so the LLM
    # knows which skills it can activate without needing to call a discovery
    # tool first.
    # NOTE: `load_skill` already triggers sandbox setup automatically for runtime
    # skills.  Use `activate_sandbox_skill` only as an explicit override —
    # e.g. to re-initialize a skill after a sandbox error, or when you need to
    # activate a skill's runtime without re-loading its instructions.
    activate_sandbox_skill.description = (
        "Explicitly activate one attached Skill's sandbox environment.\n\n"
        "Normally you do NOT need to call this tool — `load_skill` automatically "
        "prepares the sandbox when the skill has `runtime == 'python-sandbox'`. "
        "Use this tool only as an explicit override: e.g. to retry sandbox setup "
        "after an error, or to activate a skill's runtime without re-loading its "
        "instructions.\n\n"
        f"Available runtime skills for this agent: {available_names}\n\n"
        "Args:\n"
        "    skill_name: Name of the skill to activate (case-insensitive)."
    )

    @tool
    def list_active_sandbox_skills() -> str:
        """List Skills currently active in the conversation sandbox.

        Returns a comma-separated list of active skill names, or a message
        indicating that no skills have been activated yet.
        """
        try:
            active = provider.list_active_skills(handle)
        except NotImplementedError:
            return "Skill listing is not supported by the current sandbox provider."
        return ", ".join(active) if active else "No Skills are active in the sandbox."

    return [activate_sandbox_skill, list_active_sandbox_skills]
