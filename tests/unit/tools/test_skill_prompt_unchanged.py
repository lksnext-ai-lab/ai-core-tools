"""Unit tests for the step_024 opt-in skill-router wiring: `resolve_prompt_skills`
(tools.skill_tools) and its callers' invariants, plus the step_024 carry-over items
explicitly deferred to this step (see .claude/specs/skills-boosted/plan.md step_025 and
the "step_024 final API" carry-over section).

No DB needed: `Skill`/`Agent` ORM instances are built in-memory (never added to a
session), exactly like tests/unit/tools/test_skill_tools.py.

Covers:
  - AC-22: golden-string test. For an agent with 3 enabled skills and
    `skill_router_enabled=False`, `resolve_prompt_skills` returns the exact same list
    object it was given (identity check — the early return is structurally
    unreachable, not just "produces the same result today"), the generated prompt
    section is byte-identical to a hardcoded golden string literal, and neither the
    injected selector nor the LLM double is ever invoked.
  - AC-23 (prompt side): a selector returning a genuine non-empty <=2 subset narrows
    the prompt; a selector returning [] falls back to the FULL unfiltered skill list
    (the step_024 H1 fix) rather than an empty prompt.
  - Tool registration is never narrowed by the router: a 3-skill catalog where the
    router selects only 2 for the prompt still has all 3 skills' `load_skill` tool
    entries registered and callable.
  - The retry-reroutes case (agent_streaming_service.py retries create_agent up to 2x):
    calling `resolve_prompt_skills` twice in succession for the same turn does not
    corrupt shared state and behaves consistently both times.
  - `skill_router_enabled` gated on key-presence in `AgentService._update_normal_agent`
    — a partial update dict omitting the key leaves the existing value untouched.
"""
from __future__ import annotations

import asyncio
import dataclasses
import random
import typing
from typing import Optional
from unittest.mock import MagicMock

import pytest

from models.agent import Agent, AgentSkill
from models.skill import Skill
from services.agent_service import AgentService
from services.skill_router_service import SkillMeta as RouterSkillMeta
from tools.skill_tools import (
    SkillMeta,
    create_skill_loader_tool,
    generate_skills_system_prompt_section,
    resolve_prompt_skills,
    snapshot_skills,
)
from tests.unit.tools.test_skill_tools import _trusted_framing_text, _unwrap_available_skills


# ---------------------------------------------------------------------------
# Helpers (mirrors tests/unit/tools/test_skill_tools.py's conventions)
# ---------------------------------------------------------------------------


def make_skill(skill_id: int, name: str, description: Optional[str] = None,
                content: str = "content", is_enabled: bool = True,
                app_id: Optional[int] = None) -> Skill:
    return Skill(
        skill_id=skill_id,
        name=name,
        description=description,
        content=content,
        is_enabled=is_enabled,
        app_id=app_id,
    )


def make_assoc(skill: Optional[Skill], agent_id: int = 1) -> AgentSkill:
    assoc = AgentSkill(agent_id=agent_id, skill_id=skill.skill_id if skill else None)
    assoc.skill = skill
    return assoc


class _CountingSelector:
    """A `selector` double matching resolve_prompt_skills's injected-callable contract
    (`Callable[[Sequence[SkillMeta], Any, Any], Awaitable[Sequence[SkillMeta]]]`)."""

    def __init__(self, result: list):
        self.result = result
        self.call_count = 0
        self.last_catalog = None
        self.last_user_message = None
        self.last_llm = None

    async def __call__(self, catalog, user_message, llm):
        self.call_count += 1
        self.last_catalog = catalog
        self.last_user_message = user_message
        self.last_llm = llm
        return self.result


class _CountingLLMDouble:
    """A stand-in for the agent's configured LLM — must never be touched when the
    router is disabled (AC-22)."""

    def __init__(self):
        self.call_count = 0

    async def ainvoke(self, *_args, **_kwargs):
        self.call_count += 1
        raise AssertionError("LLM double must not be invoked when skill_router_enabled is False")


# ---------------------------------------------------------------------------
# AC-22 — golden-string test: flag off is byte-identical to pre-router output
# ---------------------------------------------------------------------------

# Captured golden literal (NOT derived by calling the function first) — a real
# content-identical comparison, not a loose "contains" check. Since review-round
# Finding 1 (and its follow-up fix), the rendered section wraps ONLY the untrusted
# bullet-list catalog with `wrap_untrusted` (a per-call random nonce in the delimiter
# tag), so the section as a whole can no longer be byte-identical end to end —
# `_unwrap_available_skills` (imported from test_skill_tools.py) extracts just that
# wrapped catalog body (and asserts the overall framing is well-formed) so this golden
# literal can still pin the bullet-list *content*. Order is alphabetical by folded name
# (Data Analysis, Email Drafting, Web Research) — generate_skills_system_prompt_section
# sorts deterministically before rendering, independent of input/association order.
_EXPECTED_GOLDEN_CATALOG_BODY = (
    "  - **Data Analysis**: Analyzes spreadsheets and datasets\n"
    "  - **Email Drafting**: Drafts professional emails\n"
    "  - **Web Research**: Performs web research summaries"
)

# The trusted, platform-authored framing that must stay OUTSIDE the wrapped block —
# see `_trusted_framing_text` (test_skill_tools.py).
_EXPECTED_GOLDEN_TRUSTED_INSTRUCTION = "use the `load_skill` tool with the skill name to load"


class TestAC22GoldenStringRouterDisabled:
    def _make_three_skills(self):
        return [
            make_skill(1, "Email Drafting", description="Drafts professional emails"),
            make_skill(2, "Data Analysis", description="Analyzes spreadsheets and datasets"),
            make_skill(3, "Web Research", description="Performs web research summaries"),
        ]

    @pytest.mark.asyncio
    async def test_flag_off_returns_the_identical_list_object(self):
        """Not just equal — the *same object*, per AC-22's structural guarantee that
        the router code path is genuinely unreachable, not merely a no-op."""
        resolved_skills = self._make_three_skills()
        agent = Agent(agent_id=1, skill_router_enabled=False)
        selector = _CountingSelector(result=[])
        llm = _CountingLLMDouble()

        result = await resolve_prompt_skills(
            resolved_skills, agent=agent, user_message="draft an email please",
            llm=llm, selector=selector,
        )

        assert result is resolved_skills
        assert selector.call_count == 0
        assert llm.call_count == 0

    @pytest.mark.asyncio
    async def test_flag_off_with_agent_none_also_returns_identical_list_and_calls_nothing(self):
        resolved_skills = self._make_three_skills()
        selector = _CountingSelector(result=[])
        llm = _CountingLLMDouble()

        result = await resolve_prompt_skills(
            resolved_skills, agent=None, user_message="draft an email please",
            llm=llm, selector=selector,
        )

        assert result is resolved_skills
        assert selector.call_count == 0
        assert llm.call_count == 0

    @pytest.mark.asyncio
    async def test_flag_off_prompt_section_is_byte_identical_to_golden_literal(self):
        resolved_skills = self._make_three_skills()
        agent = Agent(agent_id=1, skill_router_enabled=False)
        selector = _CountingSelector(result=[])

        prompt_skills = await resolve_prompt_skills(
            resolved_skills, agent=agent, user_message="draft an email please",
            llm=None, selector=selector,
        )
        snapshots = snapshot_skills(prompt_skills)
        section = generate_skills_system_prompt_section(snapshots)

        assert _unwrap_available_skills(section) == _EXPECTED_GOLDEN_CATALOG_BODY
        assert _EXPECTED_GOLDEN_TRUSTED_INSTRUCTION in _trusted_framing_text(section)
        # And that trusted instruction text is never inside the wrapped catalog body.
        assert "load_skill" not in _unwrap_available_skills(section)
        assert selector.call_count == 0

    @pytest.mark.asyncio
    async def test_flag_off_load_skill_tool_map_is_unaffected_and_loads_every_skill(self):
        """The tool's skill map is identical to the pre-router-feature output: every
        one of the 3 skills remains individually loadable by name."""
        resolved_skills = self._make_three_skills()
        agent = Agent(agent_id=1, skill_router_enabled=False)
        selector = _CountingSelector(result=[])

        prompt_skills = await resolve_prompt_skills(
            resolved_skills, agent=agent, user_message="draft an email please",
            llm=None, selector=selector,
        )
        snapshots = snapshot_skills(prompt_skills)
        tool = create_skill_loader_tool(snapshots)
        assert tool is not None

        for name in ("Email Drafting", "Data Analysis", "Web Research"):
            result = tool.invoke({"skill_name": name})
            assert f"[SKILL ACTIVATED: {name}]" in result

        assert selector.call_count == 0

    @pytest.mark.asyncio
    async def test_flag_off_with_missing_attribute_treated_as_falsy(self):
        """A duck-typed agent-like object without the attribute at all must also take
        the early-return path (`getattr(agent, 'skill_router_enabled', False)`)."""

        class BareAgent:
            pass

        resolved_skills = self._make_three_skills()
        selector = _CountingSelector(result=[])

        result = await resolve_prompt_skills(
            resolved_skills, agent=BareAgent(), user_message="hi", llm=None, selector=selector,
        )

        assert result is resolved_skills
        assert selector.call_count == 0


# ---------------------------------------------------------------------------
# AC-23 (prompt side) — narrowing vs. fail-open on empty selection
# ---------------------------------------------------------------------------


class TestAC23RouterEnabledNarrowingAndFailOpen:
    def _make_three_skills(self):
        return [
            make_skill(1, "Email Drafting", description="Drafts professional emails"),
            make_skill(2, "Data Analysis", description="Analyzes spreadsheets and datasets"),
            make_skill(3, "Web Research", description="Performs web research summaries"),
        ]

    @pytest.mark.asyncio
    async def test_non_empty_selector_result_narrows_the_prompt_to_that_subset(self):
        resolved_skills = self._make_three_skills()
        agent = Agent(agent_id=1, skill_router_enabled=True)
        narrowed = [SkillMeta(skill_id=1, name="Email Drafting"), SkillMeta(skill_id=2, name="Data Analysis")]
        selector = _CountingSelector(result=narrowed)

        result = await resolve_prompt_skills(
            resolved_skills, agent=agent, user_message="draft an email", llm=None, selector=selector,
        )

        assert selector.call_count == 1
        assert {s.skill_id for s in result} == {1, 2}
        assert len(result) == 2  # <= MAX_SELECTED_SKILLS (2), matches select_skills's own cap

    @pytest.mark.asyncio
    async def test_empty_selector_result_falls_back_to_the_full_unfiltered_list(self):
        """H1 fix (step_024): an empty selection must NOT narrow the prompt to nothing
        — it must fall back to the full resolved set. A test asserting a
        narrowed/empty prompt here would fail by design, per the plan's explicit
        warning."""
        resolved_skills = self._make_three_skills()
        agent = Agent(agent_id=1, skill_router_enabled=True)
        selector = _CountingSelector(result=[])

        result = await resolve_prompt_skills(
            resolved_skills, agent=agent, user_message="", llm=None, selector=selector,
        )

        assert selector.call_count == 1
        assert result is resolved_skills
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_missing_selector_falls_back_to_full_list_without_crashing(self):
        resolved_skills = self._make_three_skills()
        agent = Agent(agent_id=1, skill_router_enabled=True)

        result = await resolve_prompt_skills(
            resolved_skills, agent=agent, user_message="hi", llm=None, selector=None,
        )

        assert result is resolved_skills

    @pytest.mark.asyncio
    async def test_selector_raising_degrades_to_full_list_never_breaks_the_turn(self):
        resolved_skills = self._make_three_skills()
        agent = Agent(agent_id=1, skill_router_enabled=True)

        async def _raising_selector(catalog, user_message, llm):
            raise RuntimeError("router exploded")

        result = await resolve_prompt_skills(
            resolved_skills, agent=agent, user_message="hi", llm=None, selector=_raising_selector,
        )

        assert result is resolved_skills

    @pytest.mark.asyncio
    async def test_empty_resolved_skills_short_circuits_before_calling_selector(self):
        agent = Agent(agent_id=1, skill_router_enabled=True)
        selector = _CountingSelector(result=[])

        result = await resolve_prompt_skills(
            [], agent=agent, user_message="hi", llm=None, selector=selector,
        )

        assert result == []
        assert selector.call_count == 0

    @pytest.mark.asyncio
    async def test_selector_returning_out_of_catalog_skill_id_falls_back_to_full_list(self):
        """Reliability-auditor's round-2 H1 finding: `selected` (the selector's raw
        return value) can be non-empty while still filtering down to nothing, if it
        names a `skill_id` that isn't actually present in `resolved_skills` (a
        stale/buggy selector, or the two independently declared `SkillMeta` dataclasses
        drifting). The `if not selected` guard alone does NOT catch this — the fix must
        check the *filtered* result, not the selector's raw output."""
        resolved_skills = self._make_three_skills()
        agent = Agent(agent_id=1, skill_router_enabled=True)
        # skill_id=99 does not exist anywhere in resolved_skills (ids 1, 2, 3).
        selector = _CountingSelector(result=[SkillMeta(skill_id=99, name="Ghost Skill")])

        result = await resolve_prompt_skills(
            resolved_skills, agent=agent, user_message="draft an email", llm=None, selector=selector,
        )

        assert selector.call_count == 1
        # Must fall back to the FULL resolved set, not an empty list.
        assert result is resolved_skills
        assert len(result) == 3


# ---------------------------------------------------------------------------
# Tool registration is never narrowed by the router (step_024 carry-over)
# ---------------------------------------------------------------------------


class TestToolRegistrationNeverNarrowedByRouter:
    @pytest.mark.asyncio
    async def test_router_narrowed_prompt_still_leaves_all_three_skills_loadable(self):
        """Mirrors tools/agentTools.py's exact wiring: skill_snapshots (FULL resolved
        set) feeds create_skill_loader_tool; only prompt_skill_snapshots (the
        router-narrowed subset) feeds the prompt section. The model must still be able
        to explicitly load_skill a skill the router didn't proactively surface."""
        resolved_skills = [
            make_skill(1, "Email Drafting", description="Drafts professional emails", content="email content"),
            make_skill(2, "Data Analysis", description="Analyzes spreadsheets", content="data content"),
            make_skill(3, "Web Research", description="Performs web research", content="research content"),
        ]
        agent = Agent(agent_id=1, skill_router_enabled=True)
        # Router only surfaces 2 of the 3 skills for the PROMPT.
        narrowed = [SkillMeta(skill_id=1, name="Email Drafting"), SkillMeta(skill_id=2, name="Data Analysis")]
        selector = _CountingSelector(result=narrowed)

        # --- mirrors agentTools.py's create_agent wiring (lines ~308-331) ---
        skill_snapshots = snapshot_skills(resolved_skills)  # FULL set -> tool registration
        prompt_skills = await resolve_prompt_skills(
            resolved_skills, agent=agent, user_message="draft an email", llm=None, selector=selector,
        )
        prompt_skill_snapshots = (
            skill_snapshots if prompt_skills is resolved_skills else snapshot_skills(prompt_skills)
        )
        skills_section = generate_skills_system_prompt_section(prompt_skill_snapshots)

        # Prompt section only names the router-narrowed 2 skills.
        assert "Email Drafting" in skills_section
        assert "Data Analysis" in skills_section
        assert "Web Research" not in skills_section

        # But the load_skill TOOL is still built from the FULL, unfiltered set — the
        # 3rd skill (not surfaced in the prompt) must still be explicitly loadable.
        loader_tool = create_skill_loader_tool(skill_snapshots)
        assert loader_tool is not None

        result = loader_tool.invoke({"skill_name": "Web Research"})
        assert "research content" in result
        assert "[SKILL ACTIVATED: Web Research]" in result

        # And the two surfaced-in-prompt skills remain loadable too.
        for name, expected_content in (
            ("Email Drafting", "email content"),
            ("Data Analysis", "data content"),
        ):
            result = loader_tool.invoke({"skill_name": name})
            assert expected_content in result


# ---------------------------------------------------------------------------
# Retry-reroutes case: resolve_prompt_skills called twice in succession for the
# same turn (agent_streaming_service.py's `for attempt in range(2)` retry loop)
# ---------------------------------------------------------------------------


class TestRepeatedInvocationNoSharedStateCorruption:
    @pytest.mark.asyncio
    async def test_calling_resolve_prompt_skills_twice_in_a_row_is_consistent_and_side_effect_free(self):
        resolved_skills = [
            make_skill(1, "Email Drafting", description="Drafts professional emails"),
            make_skill(2, "Data Analysis", description="Analyzes spreadsheets"),
            make_skill(3, "Web Research", description="Performs web research"),
        ]
        original_ids = [s.skill_id for s in resolved_skills]
        agent = Agent(agent_id=1, skill_router_enabled=True)
        narrowed = [SkillMeta(skill_id=1, name="Email Drafting"), SkillMeta(skill_id=2, name="Data Analysis")]

        selector_attempt_1 = _CountingSelector(result=narrowed)
        result_1 = await resolve_prompt_skills(
            resolved_skills, agent=agent, user_message="draft an email", llm=None,
            selector=selector_attempt_1,
        )

        # A fresh selector instance for "attempt 2", matching how agentTools.py's
        # create_agent is re-invoked from scratch on retry (no cross-attempt state is
        # threaded through the router).
        selector_attempt_2 = _CountingSelector(result=narrowed)
        result_2 = await resolve_prompt_skills(
            resolved_skills, agent=agent, user_message="draft an email", llm=None,
            selector=selector_attempt_2,
        )

        assert [s.skill_id for s in result_1] == [s.skill_id for s in result_2] == [1, 2]
        assert selector_attempt_1.call_count == 1
        assert selector_attempt_2.call_count == 1
        # resolved_skills itself must never be mutated by either call.
        assert [s.skill_id for s in resolved_skills] == original_ids

    @pytest.mark.asyncio
    async def test_second_attempt_with_a_differently_routed_selection_does_not_crash(self):
        """A retry that re-invokes the router and gets a genuinely different selection
        (a different LLM sample) must still behave correctly — bounded, no crash."""
        resolved_skills = [
            make_skill(1, "Email Drafting", description="Drafts professional emails"),
            make_skill(2, "Data Analysis", description="Analyzes spreadsheets"),
            make_skill(3, "Web Research", description="Performs web research"),
        ]
        agent = Agent(agent_id=1, skill_router_enabled=True)

        selector_1 = _CountingSelector(result=[SkillMeta(skill_id=1, name="Email Drafting")])
        result_1 = await resolve_prompt_skills(
            resolved_skills, agent=agent, user_message="draft an email", llm=None, selector=selector_1,
        )

        selector_2 = _CountingSelector(result=[SkillMeta(skill_id=3, name="Web Research")])
        result_2 = await resolve_prompt_skills(
            resolved_skills, agent=agent, user_message="draft an email", llm=None, selector=selector_2,
        )

        assert [s.skill_id for s in result_1] == [1]
        assert [s.skill_id for s in result_2] == [3]


# ---------------------------------------------------------------------------
# skill_router_enabled gated on key-presence in AgentService._update_normal_agent
# ---------------------------------------------------------------------------


class TestSkillRouterEnabledKeyPresenceGate:
    def test_partial_update_omitting_the_key_leaves_existing_value_untouched(self):
        service = AgentService()
        agent = Agent(agent_id=1, skill_router_enabled=True)
        db = MagicMock()

        # A partial update dict that never mentions skill_router_enabled at all.
        service._update_normal_agent(db, agent, {"name": "Renamed", "app_id": 1})

        assert agent.skill_router_enabled is True

    def test_explicit_false_in_the_update_dict_disables_it(self):
        service = AgentService()
        agent = Agent(agent_id=1, skill_router_enabled=True)
        db = MagicMock()

        service._update_normal_agent(
            db, agent, {"name": "Renamed", "app_id": 1, "skill_router_enabled": False},
        )

        assert agent.skill_router_enabled is False

    def test_explicit_true_in_the_update_dict_enables_it(self):
        service = AgentService()
        agent = Agent(agent_id=1, skill_router_enabled=False)
        db = MagicMock()

        service._update_normal_agent(
            db, agent, {"name": "Renamed", "app_id": 1, "skill_router_enabled": True},
        )

        assert agent.skill_router_enabled is True


# ---------------------------------------------------------------------------
# Concurrency / isolation: distinct interleaved calls must never bleed state
# (reliability-auditor's proof that the sequential-only test class above is
# structurally blind to interleaving bugs)
# ---------------------------------------------------------------------------


class TestConcurrentInvocationIsolation:
    @pytest.mark.asyncio
    async def test_twenty_concurrent_calls_with_distinct_agents_never_cross_contaminate(self):
        """~20 concurrent `resolve_prompt_skills` calls, each with its own distinct
        agent/catalog and a selector that awaits a small random sleep before returning
        — proves each call's result maps back only to its own input, with no
        cross-call/cross-tenant state bleed even under real interleaving."""
        random.seed(1234)
        n_calls = 20

        async def _run(call_index: int):
            # Each call gets its own distinct 3-skill catalog (globally unique skill_ids)
            # so a cross-call bleed would be trivially detectable.
            base_id = call_index * 10
            resolved_skills = [
                make_skill(base_id + 1, f"Skill-{call_index}-A", description="a"),
                make_skill(base_id + 2, f"Skill-{call_index}-B", description="b"),
                make_skill(base_id + 3, f"Skill-{call_index}-C", description="c"),
            ]
            agent = Agent(agent_id=call_index, skill_router_enabled=True)

            async def _selector(catalog, user_message, llm):
                await asyncio.sleep(random.uniform(0, 0.02))
                # Only ever select from this call's own catalog.
                return [catalog[0]]

            result = await resolve_prompt_skills(
                resolved_skills, agent=agent, user_message=f"msg-{call_index}",
                llm=None, selector=_selector,
            )
            return call_index, base_id, result

        outcomes = await asyncio.gather(*(_run(i) for i in range(n_calls)))

        for call_index, base_id, result in outcomes:
            # Exactly the first skill of THIS call's own catalog, never another call's.
            assert len(result) == 1
            assert result[0].skill_id == base_id + 1
            assert result[0].name == f"Skill-{call_index}-A"


# ---------------------------------------------------------------------------
# Field-parity tripwire: the two independently-declared SkillMeta dataclasses
# (this module and services/skill_router_service.py) must never drift silently
# ---------------------------------------------------------------------------


class TestSkillMetaFieldParityTripwire:
    def test_skill_tools_and_router_service_skill_meta_have_identical_fields(self):
        """`tools.skill_tools.SkillMeta` and `services.skill_router_service.SkillMeta`
        are deliberately re-declared independently (see the docstring on
        `tools.skill_tools.SkillMeta` — DB/service-free layering discipline), but they
        must stay structurally identical. A future drift here would silently degrade
        the router (e.g. a `resolve_prompt_skills` selector built from one shape being
        fed a catalog built from the other) instead of failing loudly. This test is the
        tripwire."""
        # `services.skill_router_service` uses `from __future__ import annotations`
        # (so its dataclass field `.type` is a string like "Optional[str]") while
        # `tools.skill_tools` does not (its field `.type` is the evaluated typing
        # object, e.g. `typing.Optional[str]`) — resolve both sides through
        # `typing.get_type_hints` so the comparison checks the actual, evaluated
        # annotation shape, not module-level future-import quirks unrelated to the
        # actual drift risk this test guards against.
        local_hints = typing.get_type_hints(SkillMeta)
        router_hints = typing.get_type_hints(RouterSkillMeta)

        local_names = [f.name for f in dataclasses.fields(SkillMeta)]
        router_names = [f.name for f in dataclasses.fields(RouterSkillMeta)]

        assert local_names == router_names
        for name in local_names:
            assert local_hints[name] == router_hints[name], (
                f"SkillMeta field '{name}' type drifted between tools.skill_tools "
                f"({local_hints[name]!r}) and services.skill_router_service "
                f"({router_hints[name]!r})"
            )
