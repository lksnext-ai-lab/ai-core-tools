"""
Unit tests — create_skill_loader_tool with sandbox auto-initialisation
========================================================================

Verification criteria (updated for Phase 4 / step 4.7-4.10):
  1. Tool returns skill content when called with a valid skill name (basic path).
  2. Tool returns an error when called with an unknown skill name.
  3. Tool is idempotent when a sandbox handle is present — a second call with
     the same skill returns "already active" without calling ``ensure_skill``
     again (keyed on handle.active_skills, survives turn boundaries).
  4. When ``sandbox_handle`` / ``sandbox_provider`` are provided and the skill
     has package files or a bootstrap script, the tool calls ``ensure_skill``.
     The ``runtime`` field no longer controls this — only content presence does.
  5. When the skill has NO package files and NO bootstrap script, ``ensure_skill``
     is NOT called even if sandbox context is available.
  6. When sandbox context is ``None`` (code interpreter disabled), the tool loads
     instructions normally without calling ``ensure_skill``.
  7. When ``ensure_skill`` raises an exception the tool surfaces an activation-
     failed message (step 4.9) rather than propagating or silently swallowing
     the error.
  8. ``generate_skills_system_prompt_section`` produces the sandbox auto-setup
     guidance without any ``runtime``-based badge.
  9. ``create_skill_loader_tool`` returns ``None`` when no valid associations exist.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_handle(sandbox_id: str = "test-sb"):
    from tools.sandbox.provider import SandboxHandle
    return SandboxHandle(
        sandbox_id=sandbox_id,
        working_dir="/tmp/sb",
        provider_name="subprocess",
        metadata={},
    )


def _make_skill_assoc(
    name: str,
    runtime: str | None = None,
    content: str = "## Instructions\nDo the thing.",
    description: str = "Test skill description.",
    files: list | None = None,
    bootstrap_script_path: str | None = None,
):
    skill = SimpleNamespace(
        name=name,
        runtime=runtime,
        content=content,
        description=description,
        files=files or [],
        bootstrap_script_path=bootstrap_script_path,
    )
    return SimpleNamespace(skill=skill)


def _package_assoc(
    name: str = "charts",
    content: str = "## Instructions\nDo the thing.",
):
    """Return a skill association with a file (triggers ensure_skill)."""
    return _make_skill_assoc(
        name, files=[SimpleNamespace(path="scripts/run.py")], content=content
    )


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
# 2. Idempotency (now keyed on handle.active_skills — step 4.7)
# ---------------------------------------------------------------------------


class TestLoadSkillIdempotency:
    def test_second_call_returns_already_active_with_handle(self):
        """Idempotency works when a sandbox handle is present."""
        from tools.skill_tools import create_skill_loader_tool

        provider = MagicMock()
        provider.ensure_skill.return_value = {
            "phases": {"files": "ok", "bootstrap": "skipped"}
        }
        handle = _make_handle()
        assoc = _package_assoc("charts")
        tool = create_skill_loader_tool([assoc], sandbox_handle=handle, sandbox_provider=provider)

        tool.invoke({"skill_name": "charts"})
        result = tool.invoke({"skill_name": "charts"})

        assert "ALREADY ACTIVE" in result
        assert "charts" in result

    def test_second_call_does_not_re_initialize_sandbox(self):
        from tools.skill_tools import create_skill_loader_tool

        provider = MagicMock()
        provider.ensure_skill.return_value = {
            "phases": {"files": "ok", "bootstrap": "skipped"}
        }
        handle = _make_handle()
        assoc = _package_assoc("charts")
        tool = create_skill_loader_tool([assoc], sandbox_handle=handle, sandbox_provider=provider)

        tool.invoke({"skill_name": "charts"})
        tool.invoke({"skill_name": "charts"})

        # ensure_skill must have been called exactly once (idempotency via active_skills)
        provider.ensure_skill.assert_called_once()

    def test_different_sandbox_id_triggers_reinit(self):
        """Changing sandbox_id (new sandbox) must re-run ensure_skill."""
        from tools.skill_tools import create_skill_loader_tool, load_skill as _load_skill

        provider = MagicMock()
        provider.ensure_skill.return_value = {
            "phases": {"files": "ok", "bootstrap": "skipped"}
        }
        handle_a = _make_handle("sbx-1")
        handle_b = _make_handle("sbx-2")
        skill = _package_assoc("charts").skill

        _load_skill(skill, handle_a, provider)  # first handle
        _load_skill(skill, handle_b, provider)  # different sandbox → should call again

        assert provider.ensure_skill.call_count == 2

    def test_idempotency_is_per_handle(self):
        """Two distinct handles each get their own activation state."""
        from tools.skill_tools import create_skill_loader_tool

        provider = MagicMock()
        provider.ensure_skill.return_value = {
            "phases": {"files": "ok", "bootstrap": "skipped"}
        }
        handle_a = _make_handle("sbx-A")
        handle_b = _make_handle("sbx-B")
        assoc = _package_assoc("charts")

        tool_a = create_skill_loader_tool([assoc], sandbox_handle=handle_a, sandbox_provider=provider)
        tool_b = create_skill_loader_tool([assoc], sandbox_handle=handle_b, sandbox_provider=provider)

        # Load in tool_a (updates handle_a.active_skills)
        tool_a.invoke({"skill_name": "charts"})

        # tool_b has a different handle — should call ensure_skill again
        result_b = tool_b.invoke({"skill_name": "charts"})
        assert "SKILL ACTIVATED" in result_b
        assert provider.ensure_skill.call_count == 2


# ---------------------------------------------------------------------------
# 3. Sandbox auto-initialisation — content presence check (step 4.8)
# ---------------------------------------------------------------------------


class TestLoadSkillSandboxAutoInit:
    def test_calls_ensure_skill_for_skill_with_files(self):
        from tools.skill_tools import create_skill_loader_tool

        provider = MagicMock()
        provider.ensure_skill.return_value = {
            "phases": {"files": "ok", "bootstrap": "skipped"}
        }
        handle = _make_handle()
        assoc = _package_assoc("word-generation")
        tool = create_skill_loader_tool([assoc], sandbox_handle=handle, sandbox_provider=provider)

        result = tool.invoke({"skill_name": "word-generation"})

        provider.ensure_skill.assert_called_once_with(handle, assoc.skill)
        assert "[SKILL ACTIVATED: word-generation]" in result
        assert "Do the thing." in result

    def test_calls_ensure_skill_for_skill_with_bootstrap(self):
        from tools.skill_tools import create_skill_loader_tool

        provider = MagicMock()
        provider.ensure_skill.return_value = {
            "phases": {"files": "ok", "bootstrap": "ok"}
        }
        handle = _make_handle()
        assoc = _make_skill_assoc(
            "boot-skill", bootstrap_script_path="scripts/boot.py", files=[]
        )
        tool = create_skill_loader_tool([assoc], sandbox_handle=handle, sandbox_provider=provider)

        tool.invoke({"skill_name": "boot-skill"})

        provider.ensure_skill.assert_called_once()

    def test_does_not_call_ensure_skill_for_prompt_only_skill(self):
        from tools.skill_tools import create_skill_loader_tool

        provider = MagicMock()
        handle = _make_handle()
        # No files, no bootstrap → prompt-only
        assoc = _make_skill_assoc("brand-voice", runtime=None)
        tool = create_skill_loader_tool([assoc], sandbox_handle=handle, sandbox_provider=provider)

        tool.invoke({"skill_name": "brand-voice"})

        provider.ensure_skill.assert_not_called()

    def test_runtime_field_alone_does_not_trigger_ensure_skill(self):
        """runtime field is ignored; only content presence matters (step 4.8)."""
        from tools.skill_tools import create_skill_loader_tool

        provider = MagicMock()
        handle = _make_handle()
        # Has runtime but NO files and NO bootstrap
        assoc = _make_skill_assoc("old-runtime-skill", runtime="python-sandbox", files=[])
        tool = create_skill_loader_tool([assoc], sandbox_handle=handle, sandbox_provider=provider)

        tool.invoke({"skill_name": "old-runtime-skill"})

        provider.ensure_skill.assert_not_called()

    def test_does_not_call_ensure_skill_when_no_sandbox_handle(self):
        from tools.skill_tools import create_skill_loader_tool

        assoc = _package_assoc("charts")
        # No sandbox context — code interpreter disabled
        tool = create_skill_loader_tool([assoc], sandbox_handle=None, sandbox_provider=None)

        result = tool.invoke({"skill_name": "charts"})

        # Should still return skill content
        assert "[SKILL ACTIVATED: charts]" in result
        assert "Do the thing." in result

    def test_does_not_call_ensure_skill_when_no_sandbox_provider(self):
        from tools.skill_tools import create_skill_loader_tool

        handle = _make_handle()
        assoc = _package_assoc("charts")
        # handle present but no provider
        tool = create_skill_loader_tool([assoc], sandbox_handle=handle, sandbox_provider=None)

        result = tool.invoke({"skill_name": "charts"})

        assert "[SKILL ACTIVATED: charts]" in result

    def test_ensure_skill_error_surfaces_activation_failed(self):
        """When ensure_skill raises, the LLM receives an ACTIVATION FAILED message (step 4.9)."""
        from tools.skill_tools import create_skill_loader_tool

        provider = MagicMock()
        provider.ensure_skill.side_effect = RuntimeError("sandbox disconnected")
        handle = _make_handle()
        assoc = _package_assoc("charts")
        tool = create_skill_loader_tool([assoc], sandbox_handle=handle, sandbox_provider=provider)

        result = tool.invoke({"skill_name": "charts"})

        # Tool must not raise
        assert result  # non-empty
        assert "ACTIVATION FAILED" in result
        assert "charts" in result


# ---------------------------------------------------------------------------
# 4. generate_skills_system_prompt_section
# ---------------------------------------------------------------------------


class TestGenerateSkillsSystemPromptSection:
    def test_skill_listed_by_name(self):
        from tools.skill_tools import generate_skills_system_prompt_section

        assocs = [_make_skill_assoc("word-generation")]
        section = generate_skills_system_prompt_section(assocs)

        assert "word-generation" in section

    def test_prompt_only_skill_has_no_runtime_badge(self):
        from tools.skill_tools import generate_skills_system_prompt_section

        assocs = [_make_skill_assoc("brand-voice", runtime=None)]
        section = generate_skills_system_prompt_section(assocs)

        skill_lines = [line for line in section.splitlines() if "brand-voice" in line]
        assert skill_lines, "Expected a line mentioning brand-voice"
        assert "*(runtime)*" not in skill_lines[0]

    def test_mentions_sandbox_auto_setup(self):
        from tools.skill_tools import generate_skills_system_prompt_section

        assocs = [_make_skill_assoc("charts")]
        section = generate_skills_system_prompt_section(assocs)

        assert "sandbox" in section.lower() or "python_repl" in section

    def test_returns_none_when_no_valid_skills(self):
        from tools.skill_tools import generate_skills_system_prompt_section

        assocs = [SimpleNamespace(skill=None)]
        result = generate_skills_system_prompt_section(assocs)

        assert result is None

    # ------------------------------------------------------------------
    # Phase 5 / step 5.5 — router mode (active_skill_names parameter)
    # ------------------------------------------------------------------

    def test_router_mode_shows_only_selected_skills(self):
        """Only router-selected skills appear when active_skill_names is provided."""
        from tools.skill_tools import generate_skills_system_prompt_section

        assocs = [
            _make_skill_assoc("charts"),
            _make_skill_assoc("reporting"),
        ]
        section = generate_skills_system_prompt_section(
            assocs, active_skill_names={"charts"}
        )
        assert section is not None
        assert "charts" in section
        assert "reporting" not in section

    def test_router_mode_includes_already_active_skill(self):
        """Skills healthy in handle appear even if not in active_skill_names."""
        from tools.skill_tools import generate_skills_system_prompt_section

        handle = _make_handle()
        # Manually mark 'reporting' as healthy in the handle
        handle.active_skills["reporting"] = {
            "sandbox_id": handle.sandbox_id,
            "phases": {"files": "ok", "bootstrap": "ok"},
        }

        assocs = [
            _make_skill_assoc("charts"),
            _make_skill_assoc("reporting"),
        ]
        section = generate_skills_system_prompt_section(
            assocs,
            active_skill_names={"charts"},
            handle=handle,
        )
        assert section is not None
        assert "charts" in section
        assert "reporting" in section  # already active → still shown

    def test_router_mode_ignores_active_skill_from_different_sandbox(self):
        """Stale active_skill state from a previous sandbox is not shown."""
        from tools.skill_tools import generate_skills_system_prompt_section

        handle = _make_handle("current-sandbox")
        handle.active_skills["reporting"] = {
            "sandbox_id": "old-sandbox",
            "phases": {"files": "ok", "bootstrap": "ok"},
        }

        assocs = [
            _make_skill_assoc("charts"),
            _make_skill_assoc("reporting"),
        ]
        section = generate_skills_system_prompt_section(
            assocs,
            active_skill_names={"charts"},
            handle=handle,
        )
        assert section is not None
        assert "charts" in section
        assert "reporting" not in section

    def test_router_mode_empty_selection_and_no_active_returns_none(self):
        """When router selects nothing and no skills are active, result is None."""
        from tools.skill_tools import generate_skills_system_prompt_section

        handle = _make_handle()
        assocs = [
            _make_skill_assoc("charts"),
            _make_skill_assoc("reporting"),
        ]
        section = generate_skills_system_prompt_section(
            assocs,
            active_skill_names=set(),
            handle=handle,
        )
        assert section is None

    def test_legacy_mode_includes_all_skills(self):
        """When active_skill_names is None, legacy behaviour: all skills shown."""
        from tools.skill_tools import generate_skills_system_prompt_section

        assocs = [
            _make_skill_assoc("charts"),
            _make_skill_assoc("reporting"),
        ]
        section = generate_skills_system_prompt_section(assocs, active_skill_names=None)
        assert "charts" in section
        assert "reporting" in section
