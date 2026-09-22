"""Unit tests for tools.skill_tools — resolve_agent_skills and its consumers.

Covers the step_013 (AD-13) contract:
  - resolve_agent_skills is the single source of truth for skill filtering
  - disabled skills are dropped
  - duplicate normalised names: first wins, byte-for-byte warning preserved
  - for an agent whose skills are ALL enabled, prompt text / tool behaviour is
    byte-identical to the pre-refactor implementation (legacy reference below)
"""
from typing import List, Optional

import pytest
from langchain_core.tools import tool as lc_tool

from models.agent import AgentSkill
from models.skill import Skill
import tools.skill_tools as skill_tools_module
from tools.skill_tools import (
    create_skill_loader_tool,
    generate_skills_system_prompt_section,
    resolve_agent_skills,
)
from utils.skill_names import fold_name


def _capture_warnings(monkeypatch) -> List[str]:
    """tools.skill_tools uses a project logger with propagate=False, so caplog
    (which listens on the root logger) never sees these records. Patch
    logger.warning directly instead, matching the pattern used elsewhere in
    this test suite (see test_prepare_agent_config.py)."""
    captured: List[str] = []
    original_warning = skill_tools_module.logger.warning

    def _capture(msg, *args, **kwargs):
        captured.append(msg % args if args else str(msg))
        return original_warning(msg, *args, **kwargs)

    monkeypatch.setattr(skill_tools_module.logger, "warning", _capture)
    return captured


def make_skill(skill_id: int, name: str, description: Optional[str] = None,
                content: str = "content", is_enabled: bool = True,
                app_id: Optional[int] = None) -> Skill:
    skill = Skill(
        skill_id=skill_id,
        name=name,
        description=description,
        content=content,
        is_enabled=is_enabled,
        app_id=app_id,
    )
    return skill


def make_assoc(skill: Optional[Skill], agent_id: int = 1) -> AgentSkill:
    assoc = AgentSkill(agent_id=agent_id, skill_id=skill.skill_id if skill else None)
    # AgentSkill.skill is a relationship; assign directly in-memory (no session needed).
    assoc.skill = skill
    return assoc


# ---------------------------------------------------------------------------
# Legacy reference implementation (pre step_013), kept only in this test file
# to assert byte-identical output for the all-enabled, no-duplicate case.
# ---------------------------------------------------------------------------

def _legacy_generate_skills_system_prompt_section(skill_associations: List[AgentSkill]) -> Optional[str]:
    if not skill_associations:
        return None

    skills_info = []
    for assoc in skill_associations:
        if assoc.skill:
            skill = assoc.skill
            description = skill.description or "No description available"
            skills_info.append(f"  - **{skill.name}**: {description}")

    if not skills_info:
        return None

    skills_list = "\n".join(skills_info)

    return f"""
<available_skills>
You have access to the following specialized skills that you can load on-demand using the `load_skill` tool:

{skills_list}

When a user's request matches one of these skills, use the `load_skill` tool with the skill name to load detailed instructions for that specific task. Only load a skill when it's relevant to the current task.
</available_skills>"""


def _legacy_create_skill_loader_tool(skill_associations: List[AgentSkill]):
    skill_map = {}
    for assoc in skill_associations:
        if not assoc.skill:
            continue
        skill = assoc.skill
        normalized_name = skill.name.lower().strip()
        existing_skill = skill_map.get(normalized_name)
        if existing_skill is not None and existing_skill is not skill:
            continue
        skill_map[normalized_name] = skill

    if not skill_map:
        return None

    available_skills = ", ".join(sorted({skill.name for skill in skill_map.values()}))

    @lc_tool
    def load_skill(skill_name: str) -> str:
        """Load specialized instructions for a skill."""
        skill_key = skill_name.lower().strip()
        if skill_key not in skill_map:
            return f"Skill '{skill_name}' not found. Available skills: {available_skills}"
        skill = skill_map[skill_key]
        return f"""[SKILL ACTIVATED: {skill.name}]

{skill.content}

---
Follow the above instructions carefully for the current task."""

    return load_skill


# ---------------------------------------------------------------------------
# resolve_agent_skills
# ---------------------------------------------------------------------------

class TestResolveAgentSkills:
    def test_preserves_order_when_all_enabled_and_unique(self):
        s1 = make_skill(1, "Alpha")
        s2 = make_skill(2, "Beta")
        s3 = make_skill(3, "Gamma")
        assocs = [make_assoc(s1), make_assoc(s2), make_assoc(s3)]

        resolved = resolve_agent_skills(assocs)

        assert resolved == [s1, s2, s3]

    def test_drops_disabled_skill(self):
        enabled = make_skill(1, "Enabled", is_enabled=True)
        disabled = make_skill(2, "Disabled", is_enabled=False)
        assocs = [make_assoc(enabled), make_assoc(disabled)]

        resolved = resolve_agent_skills(assocs)

        assert resolved == [enabled]

    def test_drops_association_with_no_loaded_skill(self):
        s1 = make_skill(1, "Alpha")
        assocs = [make_assoc(s1), make_assoc(None)]

        resolved = resolve_agent_skills(assocs)

        assert resolved == [s1]

    def test_duplicate_normalised_name_first_wins_and_warns(self, monkeypatch):
        captured = _capture_warnings(monkeypatch)
        first = make_skill(1, "  Research  ")
        second = make_skill(2, "research")
        assocs = [make_assoc(first), make_assoc(second)]

        resolved = resolve_agent_skills(assocs)

        assert resolved == [first]
        assert any("Duplicate skill name detected after normalization" in msg for msg in captured)

    def test_no_warning_when_no_duplicates(self, monkeypatch):
        captured = _capture_warnings(monkeypatch)
        s1 = make_skill(1, "Alpha")
        s2 = make_skill(2, "Beta")
        assocs = [make_assoc(s1), make_assoc(s2)]

        resolved = resolve_agent_skills(assocs)

        assert resolved == [s1, s2]
        assert not any("Duplicate skill name detected after normalization" in msg for msg in captured)

    def test_empty_associations_returns_empty_list(self):
        assert resolve_agent_skills([]) == []


# ---------------------------------------------------------------------------
# generate_skills_system_prompt_section
# ---------------------------------------------------------------------------

class TestGenerateSkillsSystemPromptSection:
    def test_none_when_no_associations(self):
        assert generate_skills_system_prompt_section([]) is None

    def test_none_when_all_associations_missing_skill(self):
        assert generate_skills_system_prompt_section([make_assoc(None)]) is None

    def test_hides_disabled_skill(self):
        enabled = make_skill(1, "Alpha", description="Does alpha things")
        disabled = make_skill(2, "Beta", description="Does beta things", is_enabled=False)
        assocs = [make_assoc(enabled), make_assoc(disabled)]

        section = generate_skills_system_prompt_section(assocs)

        assert section is not None
        assert "Alpha" in section
        assert "Beta" not in section

    def test_byte_identical_to_legacy_when_all_enabled_and_unique(self):
        skills = [
            make_skill(1, "Alpha", description="Does alpha things"),
            make_skill(2, "Beta", description=None),
            make_skill(3, "Gamma", description="Does gamma things"),
        ]
        assocs = [make_assoc(skill) for skill in skills]

        legacy_output = _legacy_generate_skills_system_prompt_section(assocs)
        new_output = generate_skills_system_prompt_section(assocs)

        assert new_output == legacy_output
        assert new_output is not None
        assert "No description available" in new_output  # Beta has no description


# ---------------------------------------------------------------------------
# create_skill_loader_tool
# ---------------------------------------------------------------------------

class TestCreateSkillLoaderTool:
    def test_none_when_no_skills(self):
        assert create_skill_loader_tool([]) is None

    def test_disabled_skill_not_loadable(self):
        enabled = make_skill(1, "Alpha", content="alpha content")
        disabled = make_skill(2, "Beta", content="beta content", is_enabled=False)
        assocs = [make_assoc(enabled), make_assoc(disabled)]

        tool = create_skill_loader_tool(assocs)
        assert tool is not None

        result = tool.invoke({"skill_name": "Beta"})
        assert "not found" in result
        available_skills_listed = result.split("Available skills:", 1)[1]
        assert "Alpha" in available_skills_listed
        assert "Beta" not in available_skills_listed

    def test_duplicate_name_keeps_first_and_warns(self, monkeypatch):
        captured = _capture_warnings(monkeypatch)
        first = make_skill(1, "Research", content="first content")
        second = make_skill(2, "research", content="second content")
        assocs = [make_assoc(first), make_assoc(second)]

        tool = create_skill_loader_tool(assocs)

        assert tool is not None
        assert any("Duplicate skill name detected after normalization" in msg for msg in captured)

        result = tool.invoke({"skill_name": "research"})
        assert "first content" in result
        assert "second content" not in result

    def test_byte_identical_to_legacy_when_all_enabled_and_unique(self):
        skills = [
            make_skill(1, "Alpha", content="alpha content"),
            make_skill(2, "Beta", content="beta content"),
        ]
        assocs = [make_assoc(skill) for skill in skills]

        legacy_tool = _legacy_create_skill_loader_tool(assocs)
        new_tool = create_skill_loader_tool(assocs)

        assert legacy_tool is not None
        assert new_tool is not None

        for skill_name in ("Alpha", "alpha", "BETA", "unknown-skill"):
            legacy_result = legacy_tool.invoke({"skill_name": skill_name})
            new_result = new_tool.invoke({"skill_name": skill_name})
            assert new_result == legacy_result


# ---------------------------------------------------------------------------
# Deterministic collision precedence (review round 1, finding 1): an app
# skill must always win over a same-named system skill regardless of
# Agent.skill_associations ordering (there is no ORDER BY on that
# relationship, so DB/iteration order is not something we may rely on).
# ---------------------------------------------------------------------------

class TestDeterministicCollisionPrecedence:
    def test_app_skill_wins_over_system_skill_regardless_of_association_order(self, monkeypatch):
        system_skill = make_skill(1, "Research", app_id=None)
        app_skill = make_skill(2, "Research", app_id=5)

        system_first = [make_assoc(system_skill), make_assoc(app_skill)]
        app_first = [make_assoc(app_skill), make_assoc(system_skill)]

        _capture_warnings(monkeypatch)
        resolved_system_first = resolve_agent_skills(system_first)
        resolved_app_first = resolve_agent_skills(app_first)

        assert resolved_system_first == [app_skill]
        assert resolved_app_first == [app_skill]

    def test_tie_between_two_system_skills_broken_by_smaller_skill_id(self, monkeypatch):
        higher_id = make_skill(5, "Research", app_id=None)
        lower_id = make_skill(2, "Research", app_id=None)

        _capture_warnings(monkeypatch)
        resolved_a = resolve_agent_skills([make_assoc(higher_id), make_assoc(lower_id)])
        resolved_b = resolve_agent_skills([make_assoc(lower_id), make_assoc(higher_id)])

        assert resolved_a == [lower_id]
        assert resolved_b == [lower_id]

    def test_tie_between_two_app_skills_broken_by_smaller_skill_id(self, monkeypatch):
        higher_id = make_skill(9, "Research", app_id=7)
        lower_id = make_skill(4, "Research", app_id=7)

        _capture_warnings(monkeypatch)
        resolved_a = resolve_agent_skills([make_assoc(higher_id), make_assoc(lower_id)])
        resolved_b = resolve_agent_skills([make_assoc(lower_id), make_assoc(higher_id)])

        assert resolved_a == [lower_id]
        assert resolved_b == [lower_id]

    def test_create_skill_loader_tool_serves_app_skill_content_on_collision(self, monkeypatch):
        system_skill = make_skill(1, "Research", app_id=None, content="platform content")
        app_skill = make_skill(2, "Research", app_id=5, content="tenant content")

        _capture_warnings(monkeypatch)
        # System skill associated first — must still lose to the app skill.
        tool = create_skill_loader_tool([make_assoc(system_skill), make_assoc(app_skill)])
        assert tool is not None

        result = tool.invoke({"skill_name": "Research"})
        assert "tenant content" in result
        assert "platform content" not in result


# ---------------------------------------------------------------------------
# fold_name usage (review round 1, finding 2): resolution and lookup must use
# the same canonical fold as the DB-level / SkillService-level name checks
# (repositories.skill_repository.fold_name), not a plain lower/strip.
# ---------------------------------------------------------------------------

class TestFoldNameUsage:
    def test_internal_whitespace_run_collides_with_hyphenated_db_form(self, monkeypatch):
        spaced = make_skill(1, "My   Skill")
        hyphenated = make_skill(2, "my-skill")
        assert fold_name(spaced.name) == fold_name(hyphenated.name) == "my-skill"

        captured = _capture_warnings(monkeypatch)
        resolved = resolve_agent_skills([make_assoc(spaced), make_assoc(hyphenated)])

        # Same app_id (None) on both -> tie broken by skill_id, spaced (id=1) wins.
        assert resolved == [spaced]
        assert any("Duplicate skill name detected after normalization" in msg for msg in captured)

    def test_load_skill_lookup_uses_fold_name(self):
        skill = make_skill(1, "My   Skill", content="whitespace-run content")
        tool = create_skill_loader_tool([make_assoc(skill)])
        assert tool is not None

        # A hyphenated variant folds to the same key as the internally-spaced
        # stored name, proving the lookup uses fold_name and not lower/strip.
        result = tool.invoke({"skill_name": "my-skill"})
        assert "whitespace-run content" in result


# ---------------------------------------------------------------------------
# No redundant warning emission per agent build (review round 1, finding 3):
# agentTools.py used to call resolve_agent_skills an extra time just to log a
# count, re-emitting every duplicate-name warning. Guard the fix here since
# both prompt and tool consumers now resolve exactly once internally.
# ---------------------------------------------------------------------------

class TestNoDuplicateWarningPerBuild:
    def test_single_tool_build_logs_warning_exactly_once_per_collision(self, monkeypatch):
        captured = _capture_warnings(monkeypatch)
        first = make_skill(1, "Research")
        second = make_skill(2, "research")
        assocs = [make_assoc(first), make_assoc(second)]

        create_skill_loader_tool(assocs)

        warnings = [msg for msg in captured if "Duplicate skill name detected after normalization" in msg]
        assert len(warnings) == 1

    def test_prompt_and_tool_each_log_their_own_single_warning_not_more(self, monkeypatch):
        """Mirrors agentTools.py's pattern of building the prompt section and the
        load_skill tool from the same association list. Each of the two calls
        resolves once internally, so a single collision must produce exactly
        two warnings total (one per call) — never three or more, which would
        indicate a redundant extra resolve_agent_skills call re-logging it."""
        captured = _capture_warnings(monkeypatch)
        first = make_skill(1, "Research")
        second = make_skill(2, "research")
        assocs = [make_assoc(first), make_assoc(second)]

        generate_skills_system_prompt_section(assocs)
        create_skill_loader_tool(assocs)

        warnings = [msg for msg in captured if "Duplicate skill name detected after normalization" in msg]
        assert len(warnings) == 2
