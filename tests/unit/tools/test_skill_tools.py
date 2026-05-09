"""
Unit tests — load_skill and _is_loaded (step 4.7 / 4.8 / 4.9)
================================================================

Tests call the standalone ``load_skill(skill, handle, provider)`` function
directly, as well as ``_is_loaded(handle, skill)`` helper.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tools.skill_tools import _is_loaded, load_skill


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_handle(sandbox_id: str = "sbx_1"):
    h = MagicMock()
    h.sandbox_id = sandbox_id
    h.active_skills = {}
    return h


def _make_skill(
    name: str = "test-skill",
    has_files: bool = True,
    has_bootstrap: bool = False,
    content: str = "Do the thing.",
):
    skill = MagicMock()
    skill.name = name
    skill.skill_id = 1
    skill.files = [MagicMock()] if has_files else []
    skill.bootstrap_script_path = "scripts/boot.py" if has_bootstrap else None
    skill.content = content
    return skill


@pytest.fixture
def mock_provider():
    p = MagicMock()
    p.ensure_skill.return_value = {"phases": {"files": "ok", "bootstrap": "skipped"}}
    return p


# ---------------------------------------------------------------------------
# _is_loaded
# ---------------------------------------------------------------------------


class TestIsLoaded:
    def test_returns_false_when_not_in_active_skills(self):
        handle = _make_handle()
        skill = _make_skill()
        assert _is_loaded(handle, skill) is False

    def test_returns_true_for_healthy_state(self):
        handle = _make_handle()
        skill = _make_skill()
        handle.active_skills[skill.name] = {
            "sandbox_id": "sbx_1",
            "phases": {"files": "ok", "bootstrap": "skipped"},
        }
        assert _is_loaded(handle, skill) is True

    def test_returns_true_when_bootstrap_ok(self):
        handle = _make_handle()
        skill = _make_skill()
        handle.active_skills[skill.name] = {
            "sandbox_id": "sbx_1",
            "phases": {"files": "ok", "bootstrap": "ok"},
        }
        assert _is_loaded(handle, skill) is True

    def test_returns_false_for_different_sandbox_id(self):
        handle = _make_handle(sandbox_id="sbx_2")
        skill = _make_skill()
        handle.active_skills[skill.name] = {
            "sandbox_id": "sbx_1",  # stale
            "phases": {"files": "ok", "bootstrap": "skipped"},
        }
        assert _is_loaded(handle, skill) is False

    def test_returns_false_when_files_failed(self):
        handle = _make_handle()
        skill = _make_skill()
        handle.active_skills[skill.name] = {
            "sandbox_id": "sbx_1",
            "phases": {"files": "failed: write error", "bootstrap": "skipped"},
        }
        assert _is_loaded(handle, skill) is False

    def test_returns_false_when_phases_empty(self):
        handle = _make_handle()
        skill = _make_skill()
        handle.active_skills[skill.name] = {"sandbox_id": "sbx_1", "phases": {}}
        assert _is_loaded(handle, skill) is False


# ---------------------------------------------------------------------------
# load_skill — idempotency
# ---------------------------------------------------------------------------


class TestLoadSkillIdempotency:
    def test_second_call_skips_ensure_skill_when_already_active(self, mock_provider):
        handle = _make_handle()
        skill = _make_skill()
        # Pre-load healthy state
        handle.active_skills[skill.name] = {
            "sandbox_id": "sbx_1",
            "phases": {"files": "ok", "bootstrap": "skipped"},
        }
        result = load_skill(skill, handle, mock_provider)
        mock_provider.ensure_skill.assert_not_called()
        assert "ALREADY ACTIVE" in result

    def test_first_call_updates_active_skills(self, mock_provider):
        handle = _make_handle()
        skill = _make_skill()

        load_skill(skill, handle, mock_provider)

        assert skill.name in handle.active_skills
        entry = handle.active_skills[skill.name]
        assert entry["sandbox_id"] == handle.sandbox_id
        assert entry["phases"]["files"] == "ok"

    def test_first_call_then_second_is_idempotent(self, mock_provider):
        handle = _make_handle()
        skill = _make_skill()

        load_skill(skill, handle, mock_provider)       # first — calls ensure_skill
        result2 = load_skill(skill, handle, mock_provider)  # second — idempotent

        mock_provider.ensure_skill.assert_called_once()
        assert "ALREADY ACTIVE" in result2

    def test_different_sandbox_id_triggers_reinit(self, mock_provider):
        handle = _make_handle("sbx_1")
        skill = _make_skill()
        handle.active_skills[skill.name] = {
            "sandbox_id": "sbx_OLD",  # stale sandbox
            "phases": {"files": "ok", "bootstrap": "skipped"},
        }
        load_skill(skill, handle, mock_provider)
        mock_provider.ensure_skill.assert_called_once()


# ---------------------------------------------------------------------------
# load_skill — content-presence check (step 4.8)
# ---------------------------------------------------------------------------


class TestLoadSkillContentPresence:
    def test_ensure_skill_called_when_files_present(self, mock_provider):
        handle = _make_handle()
        skill = _make_skill(has_files=True, has_bootstrap=False)
        load_skill(skill, handle, mock_provider)
        mock_provider.ensure_skill.assert_called_once_with(handle, skill)

    def test_ensure_skill_called_when_bootstrap_present(self, mock_provider):
        handle = _make_handle()
        skill = _make_skill(has_files=False, has_bootstrap=True)
        load_skill(skill, handle, mock_provider)
        mock_provider.ensure_skill.assert_called_once_with(handle, skill)

    def test_ensure_skill_not_called_for_prompt_only(self, mock_provider):
        handle = _make_handle()
        skill = _make_skill(has_files=False, has_bootstrap=False)
        load_skill(skill, handle, mock_provider)
        mock_provider.ensure_skill.assert_not_called()

    def test_ensure_skill_not_called_when_handle_is_none(self, mock_provider):
        skill = _make_skill(has_files=True)
        result = load_skill(skill, None, mock_provider)
        mock_provider.ensure_skill.assert_not_called()
        assert "[SKILL ACTIVATED:" in result

    def test_ensure_skill_not_called_when_provider_is_none(self):
        handle = _make_handle()
        skill = _make_skill(has_files=True)
        result = load_skill(skill, handle, None)
        assert "[SKILL ACTIVATED:" in result


# ---------------------------------------------------------------------------
# load_skill — phase status surfacing (step 4.9)
# ---------------------------------------------------------------------------


class TestLoadSkillPhaseStatus:
    def test_file_failure_returns_activation_failed(self, mock_provider):
        handle = _make_handle()
        skill = _make_skill()
        mock_provider.ensure_skill.return_value = {
            "phases": {"files": "failed: write error", "bootstrap": "skipped"},
        }
        result = load_skill(skill, handle, mock_provider)
        assert "ACTIVATION FAILED" in result
        assert skill.name in result

    def test_file_failure_not_marked_loaded(self, mock_provider):
        handle = _make_handle()
        skill = _make_skill()
        mock_provider.ensure_skill.return_value = {
            "phases": {"files": "failed: write error", "bootstrap": "skipped"},
        }
        load_skill(skill, handle, mock_provider)
        assert _is_loaded(handle, skill) is False

    def test_bootstrap_failure_surfaces_warning_in_content(self, mock_provider):
        handle = _make_handle()
        skill = _make_skill()
        mock_provider.ensure_skill.return_value = {
            "phases": {"files": "ok", "bootstrap": "failed: script error"},
        }
        result = load_skill(skill, handle, mock_provider)
        assert "bootstrap=failed:" in result
        assert skill.content in result

    def test_bootstrap_failure_skill_still_activated(self, mock_provider):
        handle = _make_handle()
        skill = _make_skill()
        mock_provider.ensure_skill.return_value = {
            "phases": {"files": "ok", "bootstrap": "failed: script error"},
        }
        result = load_skill(skill, handle, mock_provider)
        # SKILL ACTIVATED is in the preamble even when bootstrap failed
        assert "[SKILL ACTIVATED:" in result

    def test_ensure_skill_exception_returns_activation_failed(self, mock_provider):
        handle = _make_handle()
        skill = _make_skill()
        mock_provider.ensure_skill.side_effect = RuntimeError("sandbox disconnected")
        result = load_skill(skill, handle, mock_provider)
        assert "ACTIVATION FAILED" in result
        assert skill.name in result

    def test_prompt_only_skill_activated_without_phase_errors(self):
        handle = _make_handle()
        skill = _make_skill(has_files=False, has_bootstrap=False)
        result = load_skill(skill, handle, None)
        assert "[SKILL ACTIVATED:" in result
        assert skill.content in result
