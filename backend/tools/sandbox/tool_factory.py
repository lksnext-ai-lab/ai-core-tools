"""
Sandbox tool factory.

``create_sandbox_repl_tool`` produces the ``python_repl`` LangChain tool
backed by whatever ``SandboxProvider`` is passed in.  The tool docstring
is kept identical to the original in ``python_sandbox_tools.py`` so the
LLM receives the same guidance as before.

``create_sandbox_skill_tools`` (IT-3) returns ``activate_sandbox_skill`` and
``list_active_sandbox_skills`` tools.  Only Skills with ``runtime == "python-sandbox"``
that are attached to the agent may be activated.
"""

from __future__ import annotations

from langchain_core.tools import tool

from .provider import SandboxProvider, SandboxHandle


def create_sandbox_repl_tool(handle: SandboxHandle, provider: SandboxProvider):
    """Return a ``python_repl`` LangChain tool bound to *handle* and *provider*.

    The returned tool is a drop-in replacement for the tool previously
    created by ``python_sandbox_tools.create_python_repl_tool``.
    """

    @tool
    def python_repl(code: str) -> str:
        """Execute Python code and return stdout + stderr.

        Use this tool to read, analyse, transform, and create files.
        Available libraries: pandas, openpyxl, numpy, os, json, csv, re, datetime.

        Files uploaded by the user are in the current working directory — reference
        them by filename only (e.g. 'report.xlsx', not a full path).

        Save output files to the current working directory and print the filename
        so the user knows what to download.

        Example:
            import pandas as pd
            df = pd.read_excel('data.xlsx')
            print(df.shape)
        """
        return provider.run_code(handle, code)

    return python_repl


def create_sandbox_skill_tools(
    handle: SandboxHandle,
    provider: SandboxProvider,
    skill_associations: list,
) -> list:
    """Return ``activate_sandbox_skill`` and ``list_active_sandbox_skills`` tools.

    Only Skills with ``runtime == "python-sandbox"`` that are attached to the
    agent (via *skill_associations*) may be activated.  Skills without a runtime
    tag are prompt-only and do not appear in the activation map.

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
        """Activate one attached Skill inside the conversation sandbox.

        Use this before running code that depends on a Skill's Python packages,
        scripts, templates, or assets.  Activation is idempotent — calling it
        again for an already-active Skill is a no-op.

        Only Skills that are explicitly attached to this agent may be activated.

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

