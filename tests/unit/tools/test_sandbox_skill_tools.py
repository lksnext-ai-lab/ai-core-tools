"""
Unit tests — IT-3 Lazy Skill Activation
=========================================

Verification criteria from the RFC:
  1. ``create_sandbox_skill_tools`` returns an empty list when no runtime-skills
     are attached to the agent.
  2. ``activate_sandbox_skill`` refuses unknown / non-runtime skills with an
     error message.
  3. ``activate_sandbox_skill`` calls ``provider.ensure_skill`` for an
     authorized skill and reports success.
  4. ``list_active_sandbox_skills`` returns whatever ``provider.list_active_skills``
     returns, formatted as a newline-separated string.
  5. ``SubprocessProvider.ensure_skill`` records the skill in
     ``handle.active_skills`` (v2 typed field).
  6. ``SubprocessProvider.list_active_skills`` returns a dict from
     ``handle.active_skills`` (v2 changed return type from list to dict).
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_handle(sandbox_id: str = "test-sandbox", working_dir: str = "/tmp/sandbox"):
    from tools.sandbox.provider import SandboxHandle
    return SandboxHandle(
        sandbox_id=sandbox_id,
        working_dir=working_dir,
        provider_name="subprocess",
        metadata={},
    )


def _make_skill_assoc(name: str, runtime: str | None = "python-sandbox"):
    """Return a mock AgentSkill association-like object."""
    skill = SimpleNamespace(name=name, runtime=runtime)
    assoc = SimpleNamespace(skill=skill)
    return assoc


# ---------------------------------------------------------------------------
# 1. create_sandbox_skill_tools — empty when no runtime skills
# ---------------------------------------------------------------------------


class TestCreateSandboxSkillToolsEmpty:
    def test_returns_empty_list_when_no_associations(self):
        from tools.sandbox.tool_factory import create_sandbox_skill_tools
        from tools.sandbox.subprocess_provider import SubprocessProvider

        handle = _make_handle()
        provider = SubprocessProvider()
        result = create_sandbox_skill_tools(handle, provider, [])
        assert result == []

    def test_returns_empty_list_when_all_skills_are_non_runtime(self):
        from tools.sandbox.tool_factory import create_sandbox_skill_tools
        from tools.sandbox.subprocess_provider import SubprocessProvider

        handle = _make_handle()
        provider = SubprocessProvider()
        assocs = [
            _make_skill_assoc("markdown-helper", runtime=None),
            _make_skill_assoc("plain-text", runtime="other-runtime"),
        ]
        result = create_sandbox_skill_tools(handle, provider, assocs)
        assert result == []

    def test_returns_two_tools_when_runtime_skills_present(self):
        from tools.sandbox.tool_factory import create_sandbox_skill_tools
        from tools.sandbox.subprocess_provider import SubprocessProvider

        handle = _make_handle()
        provider = SubprocessProvider()
        assocs = [_make_skill_assoc("word-generation")]
        tools = create_sandbox_skill_tools(handle, provider, assocs)
        assert len(tools) == 2
        tool_names = {t.name for t in tools}
        assert "activate_sandbox_skill" in tool_names
        assert "list_active_sandbox_skills" in tool_names


# ---------------------------------------------------------------------------
# 2. activate_sandbox_skill — authorization
# ---------------------------------------------------------------------------


class TestActivateSandboxSkillAuth:
    def _get_activate_tool(self, assocs):
        from tools.sandbox.tool_factory import create_sandbox_skill_tools
        from tools.sandbox.subprocess_provider import SubprocessProvider

        handle = _make_handle()
        provider = SubprocessProvider()
        tools = create_sandbox_skill_tools(handle, provider, assocs)
        return next(t for t in tools if t.name == "activate_sandbox_skill"), handle

    def test_refuses_unknown_skill(self):
        assocs = [_make_skill_assoc("word-generation")]
        tool, _ = self._get_activate_tool(assocs)
        result = tool.invoke({"skill_name": "data-analysis"})
        assert "not available" in result.lower() or "not allowed" in result.lower() or "not found" in result.lower() or "error" in result.lower()

    def test_refuses_non_runtime_skill_by_name(self):
        assocs = [_make_skill_assoc("word-generation", runtime=None)]
        # No runtime skills → no tools should be returned; use mixed list
        from tools.sandbox.tool_factory import create_sandbox_skill_tools
        from tools.sandbox.subprocess_provider import SubprocessProvider

        handle = _make_handle()
        provider = SubprocessProvider()
        assocs_mixed = [
            _make_skill_assoc("word-generation"),
            _make_skill_assoc("no-runtime-skill", runtime=None),
        ]
        tools = create_sandbox_skill_tools(handle, provider, assocs_mixed)
        activate = next(t for t in tools if t.name == "activate_sandbox_skill")
        result = activate.invoke({"skill_name": "no-runtime-skill"})
        assert "not available" in result.lower() or "not allowed" in result.lower() or "error" in result.lower()


# ---------------------------------------------------------------------------
# 3. activate_sandbox_skill — calls provider.ensure_skill
# ---------------------------------------------------------------------------


class TestActivateSandboxSkillSuccess:
    def test_calls_ensure_skill_and_returns_success(self):
        from tools.sandbox.tool_factory import create_sandbox_skill_tools
        from tools.sandbox.subprocess_provider import SubprocessProvider

        handle = _make_handle()
        provider = SubprocessProvider()
        assocs = [_make_skill_assoc("word-generation")]
        tools = create_sandbox_skill_tools(handle, provider, assocs)
        activate = next(t for t in tools if t.name == "activate_sandbox_skill")

        result = activate.invoke({"skill_name": "word-generation"})
        assert "word-generation" in result
        # Verify recorded in v2 active_skills field
        assert "word-generation" in handle.active_skills

    def test_handles_not_implemented_error_gracefully(self):
        from tools.sandbox.tool_factory import create_sandbox_skill_tools

        mock_provider = MagicMock()
        mock_provider.ensure_skill.side_effect = NotImplementedError("no-op")

        handle = _make_handle()
        assocs = [_make_skill_assoc("word-generation")]
        tools = create_sandbox_skill_tools(handle, mock_provider, assocs)
        activate = next(t for t in tools if t.name == "activate_sandbox_skill")

        result = activate.invoke({"skill_name": "word-generation"})
        # Should not raise; should return some graceful message
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# 4. list_active_sandbox_skills
# ---------------------------------------------------------------------------


class TestListActiveSandboxSkills:
    def test_returns_empty_message_when_none_activated(self):
        from tools.sandbox.tool_factory import create_sandbox_skill_tools
        from tools.sandbox.subprocess_provider import SubprocessProvider

        handle = _make_handle()
        provider = SubprocessProvider()
        assocs = [_make_skill_assoc("charts")]
        tools = create_sandbox_skill_tools(handle, provider, assocs)
        list_tool = next(t for t in tools if t.name == "list_active_sandbox_skills")

        result = list_tool.invoke({})
        assert isinstance(result, str)
        # No activated skills yet
        assert "charts" not in result

    def test_returns_skill_after_activation(self):
        from tools.sandbox.tool_factory import create_sandbox_skill_tools
        from tools.sandbox.subprocess_provider import SubprocessProvider

        handle = _make_handle()
        provider = SubprocessProvider()
        assocs = [_make_skill_assoc("charts")]
        tools = create_sandbox_skill_tools(handle, provider, assocs)
        activate = next(t for t in tools if t.name == "activate_sandbox_skill")
        list_tool = next(t for t in tools if t.name == "list_active_sandbox_skills")

        activate.invoke({"skill_name": "charts"})
        result = list_tool.invoke({})
        assert "charts" in result

    def test_handles_not_implemented_gracefully(self):
        from tools.sandbox.tool_factory import create_sandbox_skill_tools

        mock_provider = MagicMock()
        mock_provider.ensure_skill.return_value = None
        mock_provider.list_active_skills.side_effect = NotImplementedError("no-op")

        handle = _make_handle()
        assocs = [_make_skill_assoc("charts")]
        tools = create_sandbox_skill_tools(handle, mock_provider, assocs)
        list_tool = next(t for t in tools if t.name == "list_active_sandbox_skills")

        result = list_tool.invoke({})
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# 5. SubprocessProvider.ensure_skill — stores in metadata
# ---------------------------------------------------------------------------


class TestSubprocessProviderEnsureSkill:
    def test_records_skill_in_metadata(self):
        from tools.sandbox.subprocess_provider import SubprocessProvider

        provider = SubprocessProvider()
        handle = _make_handle()
        skill = SimpleNamespace(name="word-generation", dependencies='["python-docx>=1.1"]')
        provider.ensure_skill(handle, skill)

        assert "word-generation" in handle.active_skills

    def test_multiple_skills_accumulated(self):
        from tools.sandbox.subprocess_provider import SubprocessProvider

        provider = SubprocessProvider()
        handle = _make_handle()
        for name in ("word-generation", "charts", "data-analysis"):
            skill = SimpleNamespace(name=name, dependencies="[]")
            provider.ensure_skill(handle, skill)

        active = handle.active_skills
        assert len(active) == 3
        assert "charts" in active

    def test_idempotent(self):
        from tools.sandbox.subprocess_provider import SubprocessProvider

        provider = SubprocessProvider()
        handle = _make_handle()
        skill = SimpleNamespace(name="charts", dependencies="[]")
        provider.ensure_skill(handle, skill)
        provider.ensure_skill(handle, skill)

        active = handle.active_skills
        assert len(active) == 1


# ---------------------------------------------------------------------------
# 6. SubprocessProvider.list_active_skills — reads from metadata
# ---------------------------------------------------------------------------


class TestSubprocessProviderListActiveSkills:
    def test_empty_when_none_activated(self):
        from tools.sandbox.subprocess_provider import SubprocessProvider

        provider = SubprocessProvider()
        handle = _make_handle()
        result = provider.list_active_skills(handle)
        # v2: returns dict, not list
        assert result == {}

    def test_returns_dict_of_skill_states(self):
        from tools.sandbox.subprocess_provider import SubprocessProvider

        provider = SubprocessProvider()
        handle = _make_handle()
        for name in ("word-generation", "charts", "data-analysis"):
            skill = SimpleNamespace(name=name, dependencies="[]")
            provider.ensure_skill(handle, skill)

        result = provider.list_active_skills(handle)
        # v2: returns dict[str, dict], not a sorted list of names
        assert isinstance(result, dict)
        assert set(result.keys()) == {"word-generation", "charts", "data-analysis"}
        for state in result.values():
            assert "phases" in state
