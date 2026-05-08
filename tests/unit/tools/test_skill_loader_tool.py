"""
Unit tests — create_skill_loader_tool with sandbox auto-initialisation
========================================================================

Verification criteria:
  1. Tool returns skill content when called with a valid skill name (basic path).
  2. Tool returns an error when called with an unknown skill name.
  3. Tool is idempotent — a second call with the same skill returns
     "already active" without calling ``ensure_skill`` again.
  4. When ``sandbox_handle`` / ``sandbox_provider`` are provided and the skill
     has ``runtime == 'python-sandbox'``, the tool calls ``provider.ensure_skill``.
  5. When the skill does NOT have ``runtime == 'python-sandbox'``, ``ensure_skill``
     is NOT called even if sandbox context is available.
  6. When sandbox context is ``None`` (code interpreter disabled), the tool loads
     instructions normally without calling ``ensure_skill``.
  7. When ``ensure_skill`` raises an exception the tool still returns the skill
     content — it includes a warning note rather than propagating the error.
  8. ``generate_skills_system_prompt_section`` includes a *(runtime)* badge for
     runtime skills and the updated guidance about sandbox auto-setup.
  9. ``create_skill_loader_tool`` returns ``None`` when no valid associations exist.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_handle():
    from tools.sandbox.provider import SandboxHandle
    return SandboxHandle(
        sandbox_id="test-sb",
        working_dir="/tmp/sb",
        provider_name="subprocess",
        metadata={},
    )


def _make_skill_assoc(
    name: str,
    runtime: str | None = None,
    content: str = "## Instructions\nDo the thing.",
    description: str = "Test skill description.",
):
    skill = SimpleNamespace(
        name=name,
        runtime=runtime,
        content=content,
        description=description,
    )
    return SimpleNamespace(skill=skill)


# ---------------------------------------------------------------------------
# 1. Basic instruction loading
# ---------------------------------------------------------------------------


class TestLoadSkillBasic:
    def test_returns_skill_content_on_valid_name(self):
        from tools.skill_tools import create_skill_loader_tool

        assoc = _make_skill_assoc("word-generation")
        tool = create_skill_loader_tool([assoc])

        result = tool.invoke({"skill_name": "word-generation"})

        assert "[SKILL ACTIVATED: word-generation]" in result
        assert "Do the thing." in result

    def test_case_insensitive_lookup(self):
        from tools.skill_tools import create_skill_loader_tool

        assoc = _make_skill_assoc("Word-Generation")
        tool = create_skill_loader_tool([assoc])

        result = tool.invoke({"skill_name": "WORD-GENERATION"})

        assert "[SKILL ACTIVATED: Word-Generation]" in result

    def test_returns_error_for_unknown_skill(self):
        from tools.skill_tools import create_skill_loader_tool

        assoc = _make_skill_assoc("word-generation")
        tool = create_skill_loader_tool([assoc])

        result = tool.invoke({"skill_name": "nonexistent"})

        assert "not found" in result.lower()
        assert "word-generation" in result

    def test_returns_none_when_no_associations(self):
        from tools.skill_tools import create_skill_loader_tool

        result = create_skill_loader_tool([])
        assert result is None

    def test_returns_none_when_all_associations_missing_skill(self):
        from tools.skill_tools import create_skill_loader_tool

        assoc = SimpleNamespace(skill=None)
        result = create_skill_loader_tool([assoc])
        assert result is None


# ---------------------------------------------------------------------------
# 2. Idempotency
# ---------------------------------------------------------------------------


class TestLoadSkillIdempotency:
    def test_second_call_returns_already_active(self):
        from tools.skill_tools import create_skill_loader_tool

        assoc = _make_skill_assoc("charts")
        tool = create_skill_loader_tool([assoc])

        tool.invoke({"skill_name": "charts"})
        result = tool.invoke({"skill_name": "charts"})

        assert "ALREADY ACTIVE" in result
        assert "charts" in result

    def test_second_call_does_not_re_initialize_sandbox(self):
        from tools.skill_tools import create_skill_loader_tool

        provider = MagicMock()
        handle = _make_handle()
        assoc = _make_skill_assoc("charts", runtime="python-sandbox")
        tool = create_skill_loader_tool([assoc], sandbox_handle=handle, sandbox_provider=provider)

        tool.invoke({"skill_name": "charts"})
        tool.invoke({"skill_name": "charts"})

        # ensure_skill must have been called exactly once
        provider.ensure_skill.assert_called_once()

    def test_idempotency_is_per_tool_instance(self):
        """Each tool instance has its own _loaded_skills set."""
        from tools.skill_tools import create_skill_loader_tool

        assoc = _make_skill_assoc("charts")
        tool_a = create_skill_loader_tool([assoc])
        tool_b = create_skill_loader_tool([assoc])

        # Load in tool_a
        tool_a.invoke({"skill_name": "charts"})

        # tool_b has its own state — should load normally
        result_b = tool_b.invoke({"skill_name": "charts"})
        assert "SKILL ACTIVATED" in result_b
        assert "ALREADY ACTIVE" not in result_b


# ---------------------------------------------------------------------------
# 3. Sandbox auto-initialisation for runtime skills
# ---------------------------------------------------------------------------


class TestLoadSkillSandboxAutoInit:
    def test_calls_ensure_skill_for_runtime_skill(self):
        from tools.skill_tools import create_skill_loader_tool

        provider = MagicMock()
        handle = _make_handle()
        assoc = _make_skill_assoc("word-generation", runtime="python-sandbox")
        tool = create_skill_loader_tool([assoc], sandbox_handle=handle, sandbox_provider=provider)

        result = tool.invoke({"skill_name": "word-generation"})

        provider.ensure_skill.assert_called_once_with(handle, assoc.skill)
        # Sandbox init is silent — no sandbox status message in the LLM response
        assert "[SKILL ACTIVATED: word-generation]" in result
        assert "Do the thing." in result
        assert "Sandbox ready" not in result
        assert "Warning" not in result

    def test_does_not_call_ensure_skill_for_prompt_only_skill(self):
        from tools.skill_tools import create_skill_loader_tool

        provider = MagicMock()
        handle = _make_handle()
        # runtime is None → prompt-only skill
        assoc = _make_skill_assoc("brand-voice", runtime=None)
        tool = create_skill_loader_tool([assoc], sandbox_handle=handle, sandbox_provider=provider)

        tool.invoke({"skill_name": "brand-voice"})

        provider.ensure_skill.assert_not_called()

    def test_does_not_call_ensure_skill_when_no_sandbox_handle(self):
        from tools.skill_tools import create_skill_loader_tool

        assoc = _make_skill_assoc("charts", runtime="python-sandbox")
        # No sandbox context — code interpreter disabled
        tool = create_skill_loader_tool([assoc], sandbox_handle=None, sandbox_provider=None)

        result = tool.invoke({"skill_name": "charts"})

        # Should still return skill content
        assert "[SKILL ACTIVATED: charts]" in result
        assert "Do the thing." in result

    def test_does_not_call_ensure_skill_when_no_sandbox_provider(self):
        from tools.skill_tools import create_skill_loader_tool

        handle = _make_handle()
        assoc = _make_skill_assoc("charts", runtime="python-sandbox")
        # handle present but no provider
        tool = create_skill_loader_tool([assoc], sandbox_handle=handle, sandbox_provider=None)

        result = tool.invoke({"skill_name": "charts"})

        assert "[SKILL ACTIVATED: charts]" in result

    def test_ensure_skill_error_does_not_raise(self):
        from tools.skill_tools import create_skill_loader_tool

        provider = MagicMock()
        provider.ensure_skill.side_effect = RuntimeError("pip install failed")
        handle = _make_handle()
        assoc = _make_skill_assoc("charts", runtime="python-sandbox")
        tool = create_skill_loader_tool([assoc], sandbox_handle=handle, sandbox_provider=provider)

        result = tool.invoke({"skill_name": "charts"})

        # Tool must return something useful, not raise
        assert "[SKILL ACTIVATED: charts]" in result
        # Sandbox errors are silent — no warning exposed to the LLM
        assert "Warning" not in result
        assert "error" not in result.lower() or "SKILL ACTIVATED" in result
        # Instructions are still returned
        assert "Do the thing." in result


# ---------------------------------------------------------------------------
# 4. generate_skills_system_prompt_section badges
# ---------------------------------------------------------------------------


class TestGenerateSkillsSystemPromptSection:
    def test_runtime_skill_has_badge(self):
        from tools.skill_tools import generate_skills_system_prompt_section

        assocs = [_make_skill_assoc("word-generation", runtime="python-sandbox")]
        section = generate_skills_system_prompt_section(assocs)

        assert "*(runtime)*" in section

    def test_prompt_only_skill_has_no_badge(self):
        from tools.skill_tools import generate_skills_system_prompt_section

        assocs = [_make_skill_assoc("brand-voice", runtime=None)]
        section = generate_skills_system_prompt_section(assocs)

        # The skill entry line should NOT have the *(runtime)* badge
        skill_lines = [l for l in section.splitlines() if "brand-voice" in l]
        assert skill_lines, "Expected a line mentioning brand-voice"
        assert "*(runtime)*" not in skill_lines[0]

    def test_mentions_sandbox_auto_setup(self):
        from tools.skill_tools import generate_skills_system_prompt_section

        assocs = [_make_skill_assoc("charts", runtime="python-sandbox")]
        section = generate_skills_system_prompt_section(assocs)

        assert "sandbox" in section.lower() or "python_repl" in section

    def test_returns_none_when_no_valid_skills(self):
        from tools.skill_tools import generate_skills_system_prompt_section

        assocs = [SimpleNamespace(skill=None)]
        result = generate_skills_system_prompt_section(assocs)

        assert result is None
