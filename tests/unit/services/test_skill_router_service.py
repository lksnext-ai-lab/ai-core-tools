"""Unit tests for services.skill_router_service — the step_023 pure, DB-free skill
pre-selection module.

No DB is needed: `select_skills`/`score_skills` are pure functions over `SkillMeta`
(metadata-only, never ORM instances). LLM calls are doubled with `RunnableLambda` so
these tests never touch a real provider.

Covers (see .claude/specs/skills-boosted/plan.md step_025 + step_023's carry-over
"Known non-blocking follow-ups" list, which explicitly deferred this module's *entire*
test coverage to this step):
  - AC-24: token-boundary keyword matching — "art" must not match "start", whole-token
    case-insensitivity, stop-words ignored, no stemming.
  - AC-23: at most MAX_SELECTED_SKILLS selected; a raising LLM double falls back to the
    deterministic keyword scorer, same input -> same output across repeated runs; the
    cap is asserted against `select_skills`'s own return value.
  - The non-raising contract under hostile input (non-str/bytes/multimodal-list
    `user_message`; a catalog with `None`/wrong-typed `SkillMeta` fields).
  - Nested `BaseExceptionGroup` handling: pure cancellation propagates, a mixed group
    falls back.
  - All 5 documented credential-leak shapes are redacted by `_scrub_exception_text`.
  - Unicode-smuggling ranges are stripped by `utils.prompt_safety` (promoted out of
    `skill_tools.py` in step_023, shared by this module).
  - A regression guard: `_fallback` must never dispatch through an executor/thread pool
    (the round-2 H1 finding — routing it through this repo's shared default
    ThreadPoolExecutor would let every sync `@tool`'s multi-minute sandbox work starve
    the router's own fallback of last resort).
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import json
import random
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from services.skill_router_service import (
    MAX_CATALOG_ENTRIES,
    MAX_DESCRIPTION_CHARS,
    MAX_SELECTED_SKILLS,
    MAX_USER_MESSAGE_CHARS,
    MAX_WHEN_TO_USE_CHARS,
    SkillMeta,
    _bind_router_timeout,
    _cap_catalog,
    _fallback,
    _scrub_exception_text,
    score_skills,
    select_skills,
)
from utils import prompt_safety


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


def _llm_returning(selected_names: list[str]) -> RunnableLambda:
    """An LLM double that succeeds with a structured JSON selection."""

    async def _invoke(_prompt_value: Any) -> AIMessage:
        return AIMessage(content=json.dumps({"selected_skill_names": selected_names}))

    return RunnableLambda(_invoke)


class _CountingRaisingLLM:
    """An LLM double that always raises, recording how many times it was invoked."""

    def __init__(self, exc_factory=lambda: RuntimeError("router LLM boom")):
        self.call_count = 0
        self._exc_factory = exc_factory

    def as_runnable(self) -> RunnableLambda:
        async def _invoke(_prompt_value: Any) -> AIMessage:
            self.call_count += 1
            raise self._exc_factory()

        return RunnableLambda(_invoke)


# ---------------------------------------------------------------------------
# AC-24 — token-boundary keyword matching (score_skills / the deterministic fallback)
# ---------------------------------------------------------------------------


class TestTokenBoundaryMatching:
    def test_art_does_not_match_inside_start(self):
        """The canonical AC-24 example: "art" must not match a description mentioning
        only "start" — substring matching would wrongly select this skill."""
        catalog = [SkillMeta(1, "Start Guide", description="How to start a new project")]

        result = score_skills(catalog, "I need help with art today")

        assert result == []

    def test_start_matches_start_as_a_whole_token(self):
        catalog = [SkillMeta(1, "Start Guide", description="How to start a new project")]

        result = score_skills(catalog, "please help me start now")

        assert [s.skill_id for s in result] == [1]

    def test_no_stemming_chart_does_not_match_charts(self):
        """Pinning exact behaviour: this is whole-token matching only, no stemming —
        the singular "chart" and the plural "charts" are different tokens and must
        NOT be treated as a match."""
        catalog = [SkillMeta(1, "Charts Skill", description="Generate charts and reports")]

        result = score_skills(catalog, "please make a chart for me")

        assert result == []

    def test_chart_matches_when_the_message_uses_the_exact_token(self):
        catalog = [SkillMeta(1, "Charts Skill", description="Generate charts and reports")]

        result = score_skills(catalog, "please make some charts for me")

        assert [s.skill_id for s in result] == [1]

    def test_case_insensitive_whole_token_match(self):
        catalog = [SkillMeta(1, "Reporting", description="START a new report workflow")]

        result = score_skills(catalog, "please START now")

        assert [s.skill_id for s in result] == [1]

    def test_stopwords_alone_select_nothing(self):
        catalog = [SkillMeta(1, "Alpha", description="the a of")]

        result = score_skills(catalog, "the is a of")

        assert result == []

    def test_stopwords_are_ignored_but_content_word_still_matches(self):
        catalog = [SkillMeta(1, "Research", description="deep research on topics")]

        result = score_skills(catalog, "please do the research for me")

        assert [s.skill_id for s in result] == [1]

    def test_empty_catalog_or_message_selects_nothing(self):
        assert score_skills([], "anything") == []
        assert score_skills([SkillMeta(1, "Alpha", description="alpha")], "") == []
        assert score_skills([SkillMeta(1, "Alpha", description="alpha")], "   ") == []

    def test_ties_broken_by_skill_name_ascending_for_determinism(self):
        catalog = [
            SkillMeta(3, "Zeta Skill", description="alpha alpha"),
            SkillMeta(1, "Alpha Skill", description="alpha alpha"),
            SkillMeta(2, "Mid Skill", description="alpha alpha"),
        ]

        result = score_skills(catalog, "alpha")

        assert [s.name for s in result] == ["Alpha Skill", "Mid Skill"]  # capped to 2


# ---------------------------------------------------------------------------
# AC-23 — cap enforcement and deterministic fallback on LLM failure
# ---------------------------------------------------------------------------


class TestCapAndFallbackDeterminism:
    @pytest.mark.asyncio
    async def test_llm_raise_falls_back_and_cap_holds_against_select_skills_return(self):
        """IMPORTANT (step_024 carry-over): assert the <=2 cap against select_skills's
        OWN return value, never against a rendered prompt string."""
        catalog = [
            SkillMeta(1, "Alpha Skill", description="alpha alpha alpha", when_to_use="alpha tasks"),
            SkillMeta(2, "Beta Skill", description="beta beta", when_to_use="beta tasks"),
            SkillMeta(3, "Gamma Skill", description="gamma", when_to_use="gamma tasks"),
        ]
        raising_llm = _CountingRaisingLLM()
        llm = raising_llm.as_runnable()

        results = []
        for _ in range(10):
            result = await select_skills(
                catalog, "I need help with alpha and beta and gamma tasks", llm
            )
            results.append(tuple(s.skill_id for s in result))

        # The LLM double was actually invoked every time (proves the fallback path was
        # genuinely exercised, not skipped).
        assert raising_llm.call_count == 10

        # Deterministic: same input -> same output across all 10 runs.
        assert len(set(results)) == 1

        # Cap enforced (AC-23), against select_skills's own return value.
        assert len(results[0]) <= MAX_SELECTED_SKILLS

        # Exact pinned outcome: Alpha/Beta/Gamma all tie at overlap=2 ("alpha"/"beta"/
        # "gamma" + "tasks"), tie-broken by name ascending -> Alpha, then Beta.
        assert results[0] == (1, 2)

    @pytest.mark.asyncio
    async def test_no_llm_configured_uses_fallback_directly_and_turn_proceeds(self):
        catalog = [SkillMeta(1, "Alpha Skill", description="alpha work")]

        result = await select_skills(catalog, "I need alpha work", None)

        assert [s.skill_id for s in result] == [1]

    @pytest.mark.asyncio
    async def test_llm_success_path_also_respects_the_cap(self):
        catalog = [
            SkillMeta(1, "Alpha Skill", description="alpha"),
            SkillMeta(2, "Beta Skill", description="beta"),
            SkillMeta(3, "Gamma Skill", description="gamma"),
        ]
        # A (hostile/buggy) LLM response naming all 3 skills — select_skills must still
        # cap at MAX_SELECTED_SKILLS.
        llm = _llm_returning(["Alpha Skill", "Beta Skill", "Gamma Skill"])

        result = await select_skills(catalog, "alpha beta gamma", llm)

        assert len(result) <= MAX_SELECTED_SKILLS
        assert [s.skill_id for s in result] == [1, 2]

    @pytest.mark.asyncio
    async def test_llm_response_naming_an_unknown_skill_is_ignored_not_injected(self):
        """The LLM's returned names are validated against the actual capped catalog via
        a fold_name-keyed whitelist — a hallucinated name can never inject an
        out-of-catalog SkillMeta into the result."""
        catalog = [SkillMeta(1, "Alpha Skill", description="alpha")]
        llm = _llm_returning(["Alpha Skill", "Totally Made Up Skill"])

        result = await select_skills(catalog, "alpha", llm)

        assert [s.skill_id for s in result] == [1]

    @pytest.mark.asyncio
    async def test_llm_timeout_falls_back_to_keyword_scoring(self, monkeypatch):
        import services.skill_router_service as router_module

        monkeypatch.setattr(router_module, "LLM_ROUTE_TIMEOUT_SECONDS", 0.05)

        async def _hangs_forever(_prompt_value: Any) -> AIMessage:
            await asyncio.sleep(5)
            return AIMessage(content="{}")

        catalog = [SkillMeta(1, "Alpha Skill", description="alpha work")]
        result = await router_module.select_skills(
            catalog, "I need alpha work", RunnableLambda(_hangs_forever)
        )

        assert [s.skill_id for s in result] == [1]


# ---------------------------------------------------------------------------
# Size-cap regressions: cost/latency and prompt-injection-surface controls that
# mutation testing proved are currently unenforced by any existing test
# ---------------------------------------------------------------------------


class TestSizeCapsActuallyMatter:
    def test_catalog_of_sixty_skills_is_capped_to_max_catalog_entries_deterministically(self):
        catalog = [
            SkillMeta(i, f"Skill-{i:02d}", description=f"desc {i}")
            for i in range(60)
        ]
        assert len(catalog) == 60

        capped = _cap_catalog(catalog)

        assert len(capped) == MAX_CATALOG_ENTRIES == 50
        # Deterministic order: sorted by name ascending.
        assert [s.name for s in capped] == sorted(s.name for s in catalog)[:MAX_CATALOG_ENTRIES]

    @pytest.mark.asyncio
    async def test_select_skills_only_considers_the_capped_catalog(self):
        """End-to-end: a keyword that only exists on a skill beyond the cap must never
        be selected, proving the cap is actually applied on the `select_skills` path,
        not just unit-testable via `_cap_catalog` in isolation."""
        # 60 skills, alphabetically sorted names "Skill-00".."Skill-59" — the cap keeps
        # only the first 50 ("Skill-00".."Skill-49"); "Skill-59" is capped away.
        catalog = [
            SkillMeta(i, f"Skill-{i:02d}", description="filler filler filler")
            for i in range(60)
        ]
        # Give the capped-away skill a unique, otherwise-unused keyword in its
        # description so a real match would be unambiguous if the cap were removed.
        catalog[59] = SkillMeta(59, "Skill-59", description="zzzuniquekeyword")

        result = await select_skills(catalog, "please find zzzuniquekeyword now", None)

        assert result == []

    def test_over_long_user_message_beyond_the_cap_is_truncated_before_scoring(self):
        """A keyword placed only beyond MAX_USER_MESSAGE_CHARS must not be found —
        proving the message is truncated before it ever reaches the scorer."""
        catalog = [SkillMeta(1, "Alpha Skill", description="alpha stuff")]
        filler = "filler " * 400  # well over MAX_USER_MESSAGE_CHARS on its own
        assert len(filler) > MAX_USER_MESSAGE_CHARS
        message = filler + "alpha"

        result = asyncio.run(select_skills(catalog, message, None))

        assert result == []

    def test_user_message_keyword_within_the_cap_is_still_found(self):
        """Sanity control for the truncation test above: the same keyword, placed
        within the retained prefix, is still matched — proving the empty result above
        is due to truncation, not some unrelated breakage."""
        catalog = [SkillMeta(1, "Alpha Skill", description="alpha stuff")]
        message = "alpha " + ("filler " * 10)

        result = asyncio.run(select_skills(catalog, message, None))

        assert [s.skill_id for s in result] == [1]

    @pytest.mark.asyncio
    async def test_over_long_description_and_when_to_use_are_truncated_in_routing_catalog_text(self):
        """Captures the exact prompt text handed to the LLM and asserts the
        over-length description/when_to_use never appear in full — proving they are
        truncated in the catalog text actually used for routing, not just internally
        capped somewhere unreachable."""
        long_desc = "d" * (MAX_DESCRIPTION_CHARS * 5)
        long_when = "w" * (MAX_WHEN_TO_USE_CHARS * 5)
        catalog = [SkillMeta(1, "Alpha Skill", description=long_desc, when_to_use=long_when)]

        captured: dict[str, str] = {}

        async def _invoke(prompt_value: Any) -> AIMessage:
            captured["text"] = prompt_value.to_string()
            return AIMessage(content=json.dumps({"selected_skill_names": ["Alpha Skill"]}))

        llm = RunnableLambda(_invoke)
        result = await select_skills(catalog, "please help", llm)

        assert [s.skill_id for s in result] == [1]
        rendered = captured["text"]
        # The full untruncated strings must never appear.
        assert long_desc not in rendered
        assert long_when not in rendered
        # A prefix strictly longer than the cap must not appear either (bounds the
        # truncation length, not just "shorter than the full string").
        assert "d" * (MAX_DESCRIPTION_CHARS + 1) not in rendered
        assert "w" * (MAX_WHEN_TO_USE_CHARS + 1) not in rendered


# ---------------------------------------------------------------------------
# Concurrency / isolation for select_skills itself — the module-level
# `_ROUTER_PROMPT`/`_OUTPUT_PARSER` singletons are never exercised concurrently
# by any existing test
# ---------------------------------------------------------------------------


class TestSelectSkillsConcurrentIsolation:
    @pytest.mark.asyncio
    async def test_twenty_concurrent_calls_with_distinct_catalogs_never_cross_contaminate(self):
        n_calls = 20

        async def _run(call_index: int):
            base_id = call_index * 10
            catalog = [
                SkillMeta(base_id + 1, f"Call{call_index}-Alpha", description=f"call{call_index}alpha stuff"),
                SkillMeta(base_id + 2, f"Call{call_index}-Beta", description=f"call{call_index}beta stuff"),
            ]

            async def _invoke(_prompt_value: Any) -> AIMessage:
                await asyncio.sleep(random.uniform(0, 0.02))
                return AIMessage(
                    content=json.dumps({"selected_skill_names": [f"Call{call_index}-Alpha"]})
                )

            llm = RunnableLambda(_invoke)
            result = await select_skills(catalog, f"need call{call_index}alpha stuff", llm)
            return call_index, base_id, result

        outcomes = await asyncio.gather(*(_run(i) for i in range(n_calls)))

        for call_index, base_id, result in outcomes:
            assert len(result) == 1
            assert result[0].skill_id == base_id + 1
            assert result[0].name == f"Call{call_index}-Alpha"


# ---------------------------------------------------------------------------
# Non-raising contract under hostile input (owed by step_023's carry-over)
# ---------------------------------------------------------------------------


class TestNonRaisingContractHostileInput:
    """select_skills is documented to never raise. Exercise it with the exact hostile
    shapes named in step_023's carry-over: non-str/bytes/multimodal-block-list
    `user_message`, and a catalog containing SkillMeta entries with None/wrong-typed
    fields."""

    _HOSTILE_CATALOG = [
        SkillMeta(1, None, description=None, when_to_use=None),
        SkillMeta(2, 12345, description=999, when_to_use=[1, 2, 3]),
        SkillMeta(3, "Alpha", description="alpha stuff", when_to_use="use for alpha"),
    ]

    @pytest.mark.asyncio
    async def test_hostile_catalog_via_fallback_path_never_raises(self):
        result = await select_skills(self._HOSTILE_CATALOG, "alpha please", None)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "hostile_message",
        [
            b"bytes message",
            12345,
            {"weird": "dict", "not": "a string"},
            [{"type": "text", "text": "alpha"}, {"type": "image_url", "image_url": "x"}],
            None,
            [b"nested", 123, {"type": "text", "text": "alpha"}],
        ],
    )
    async def test_hostile_user_message_shapes_never_raise(self, hostile_message):
        llm = _llm_returning(["Alpha"])
        result = await select_skills(self._HOSTILE_CATALOG, hostile_message, llm)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_hostile_user_message_via_llm_path_with_valid_catalog_never_raises(self):
        catalog = [SkillMeta(1, "Alpha", description="alpha stuff")]
        llm = _llm_returning(["Alpha"])
        for hostile_message in (b"x", 1, {"a": 1}, [{"type": "image_url"}]):
            result = await select_skills(catalog, hostile_message, llm)
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_hostile_catalog_with_valid_names_but_bad_description_types(self):
        """Isolates non-str description/when_to_use (name still a valid str) — must not
        raise on either the LLM path or the fallback path."""
        catalog = [
            SkillMeta(1, "Alpha", description=999, when_to_use=[1, 2, 3]),
            SkillMeta(2, "Beta", description=None, when_to_use=None),
        ]
        result_fallback = await select_skills(catalog, "need alpha help", None)
        assert [s.skill_id for s in result_fallback] == [1]

        llm = _llm_returning(["Alpha"])
        result_llm = await select_skills(catalog, "need alpha help", llm)
        assert isinstance(result_llm, list)

    def test_empty_catalog_short_circuits_without_touching_message_or_llm(self):
        """`select_skills([], ...)` must return [] immediately — covered here as a
        cheap sync sanity check alongside the async hostile-input tests above."""
        assert asyncio.run(select_skills([], "anything", object())) == []


# ---------------------------------------------------------------------------
# Nested BaseExceptionGroup handling
# ---------------------------------------------------------------------------


class TestBaseExceptionGroupHandling:
    @pytest.mark.asyncio
    async def test_pure_cancellation_group_propagates_at_multiple_nesting_depths(self):
        """A BaseExceptionGroup whose every leaf is CancelledError (nested 4+ levels
        deep) must propagate — genuine cancellation must never be swallowed. Bumped
        from depth 3 to depth 4 — prior review rounds verified the real `exc.split()`
        recursion works at least that deep; the test should pin at least that far."""

        async def _raise_pure_cancellation(_prompt_value: Any) -> AIMessage:
            raise BaseExceptionGroup(
                "outer",
                [
                    BaseExceptionGroup(
                        "middle",
                        [
                            BaseExceptionGroup(
                                "inner",
                                [
                                    BaseExceptionGroup(
                                        "innermost",
                                        [asyncio.CancelledError(), asyncio.CancelledError()],
                                    ),
                                    asyncio.CancelledError(),
                                ],
                            ),
                            asyncio.CancelledError(),
                        ],
                    ),
                    asyncio.CancelledError(),
                ],
            )

        catalog = [SkillMeta(1, "Alpha")]
        llm = RunnableLambda(_raise_pure_cancellation)

        with pytest.raises(BaseExceptionGroup):
            await select_skills(catalog, "please help", llm)

    @pytest.mark.asyncio
    async def test_mixed_exception_group_falls_back_to_keyword_scorer(self):
        """A BaseExceptionGroup with at least one non-cancellation leaf (nested) must
        NOT propagate — it falls back like any other failure."""

        async def _raise_mixed(_prompt_value: Any) -> AIMessage:
            raise BaseExceptionGroup(
                "outer",
                [
                    BaseExceptionGroup(
                        "inner", [asyncio.CancelledError(), RuntimeError("boom")]
                    ),
                    asyncio.CancelledError(),
                ],
            )

        catalog = [SkillMeta(1, "Alpha Skill", description="alpha work")]
        llm = RunnableLambda(_raise_mixed)

        result = await select_skills(catalog, "I need alpha work", llm)

        assert [s.skill_id for s in result] == [1]

    @pytest.mark.asyncio
    async def test_flat_single_level_cancelled_error_group_propagates(self):
        async def _raise_flat(_prompt_value: Any) -> AIMessage:
            raise BaseExceptionGroup("flat", [asyncio.CancelledError()])

        catalog = [SkillMeta(1, "Alpha")]
        llm = RunnableLambda(_raise_flat)

        with pytest.raises(BaseExceptionGroup):
            await select_skills(catalog, "please help", llm)


# ---------------------------------------------------------------------------
# Credential-leak shapes redacted by _scrub_exception_text
# ---------------------------------------------------------------------------


class TestCredentialScrubbing:
    @pytest.mark.parametrize(
        "raw,leaked_fragment",
        [
            ("Authorization: Bearer sk-xyz999", "sk-xyz999"),
            ("Incorrect API key provided: sk-abc123def.", "sk-abc123def"),
            ("{'Authorization': 'Bearer sk-live-SECRET'}", "sk-live-SECRET"),
            ('{"api_key": "sk-proj-SECRET"}', "sk-proj-SECRET"),
            (
                "https://user:sk-live-SECRET@proxy.internal:8443/v1",
                "sk-live-SECRET",
            ),
        ],
    )
    def test_each_documented_leak_shape_is_redacted(self, raw, leaked_fragment):
        scrubbed = _scrub_exception_text(raw)

        assert leaked_fragment not in scrubbed
        assert "<redacted>" in scrubbed

    def test_scrubbing_truncates_to_max_len(self):
        raw = "x" * 1000
        assert len(_scrub_exception_text(raw, max_len=50)) == 50

    def test_scrubbing_handles_empty_and_none_gracefully(self):
        assert _scrub_exception_text("") == ""

    # -----------------------------------------------------------------
    # Layer isolation: the mutation-testing finding was that deleting EITHER the
    # keyword-based layer OR the query-string layer independently still left all
    # prior tests green, because every prior case also happened to contain a
    # `sk-`-style token the shape layer alone would catch. These cases are crafted
    # so only ONE layer can possibly redact them.
    # -----------------------------------------------------------------

    def test_keyword_only_shape_with_no_recognizable_key_prefix_is_redacted(self):
        """No `sk-`/`AIza`/etc. shape anywhere in this string — only the
        keyword-based layer can redact it. If that layer is deleted, this fails."""
        raw = "password: hunter2"

        scrubbed = _scrub_exception_text(raw)

        assert "hunter2" not in scrubbed
        assert "<redacted>" in scrubbed

    def test_query_string_only_shape_with_a_non_recognized_token_is_redacted(self):
        """The token here (`SOMETOKEN123`) matches no known shape prefix, and `key` in
        `api_key` has no preceding word boundary for the keyword regex (`_key` — no
        boundary between `_` and `k`) — only the query-string layer can redact this."""
        raw = "GET https://example.com/foo?api_key=SOMETOKEN123&x=1 -> 401"

        scrubbed = _scrub_exception_text(raw)

        assert "SOMETOKEN123" not in scrubbed
        assert "<redacted>" in scrubbed

    @pytest.mark.parametrize(
        "raw,leaked_fragment",
        [
            ("Response body: AIzaSyD3916SDFsdf0DFSDFDSF end", "AIzaSyD3916SDFsdf0DFSDFDSF"),
            ("Slack replied with xoxb-not-a-real-secret-000000 in payload", "xoxb-not-a-real-secret-000000"),
            ("GitHub returned ghp-1234567890abcdefghijklmnopqrstuvwxyz in body", "ghp-1234567890abcdefghijklmnopqrstuvwxyz"),
            ("JWT dump: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 end", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"),
        ],
    )
    def test_previously_unexercised_shape_prefixes_are_redacted(self, raw, leaked_fragment):
        """AIza (Google), xoxb- (Slack bot), ghp- (GitHub PAT), eyJ (JWT) — documented
        shape prefixes that no prior test actually exercised."""
        scrubbed = _scrub_exception_text(raw)

        assert leaked_fragment not in scrubbed
        assert "<redacted>" in scrubbed


# ---------------------------------------------------------------------------
# Unicode smuggling ranges stripped (backend/utils/prompt_safety.py — promoted out
# of skill_tools.py in step_023, shared with this module)
# ---------------------------------------------------------------------------


class TestUnicodeSmugglingStripped:
    def test_unicode_tag_block_is_stripped(self):
        # U+E0000-E007F: the invisible ASCII-smuggling "Unicode tag block".
        smuggled = chr(0xE0001) + chr(0xE0042) + chr(0xE007F)
        sample = "before" + smuggled + "after"

        cleaned = prompt_safety.sanitize_untrusted_text(sample)

        assert cleaned == "beforeafter"
        for cp in (0xE0001, 0xE0042, 0xE007F):
            assert chr(cp) not in cleaned

    def test_bidi_isolates_are_stripped(self):
        # U+2066-2069: bidi isolates (the "Trojan Source" half not covered by the
        # classic bidi-override range).
        sample = "before" + chr(0x2066) + "hidden" + chr(0x2069) + "after"

        cleaned = prompt_safety.sanitize_untrusted_text(sample)

        assert cleaned == "beforehiddenafter"

    def test_zero_width_and_bom_chars_stripped(self):
        sample = "a" + chr(0x200B) + "b" + chr(0xFEFF) + "c"

        cleaned = prompt_safety.sanitize_untrusted_text(sample)

        assert cleaned == "abc"

    def test_bidi_override_embedding_controls_stripped(self):
        # U+202A-202E: bidi embedding/override controls (classic "Trojan Source").
        sample = "before" + chr(0x202E) + "reversed" + chr(0x202C) + "after"

        cleaned = prompt_safety.sanitize_untrusted_text(sample)

        assert cleaned == "beforereversedafter"

    def test_tabs_newlines_and_carriage_returns_are_preserved(self):
        sample = "line1\tindented\nline2\r\n"

        cleaned = prompt_safety.sanitize_untrusted_text(sample)

        assert cleaned == sample

    def test_wrap_untrusted_also_strips_smuggling_from_the_body(self):
        smuggled = "hello" + chr(0xE0001) + chr(0x2066) + chr(0x200B) + "world"

        wrapped = prompt_safety.wrap_untrusted("user_message", smuggled)

        assert chr(0xE0001) not in wrapped
        assert chr(0x2066) not in wrapped
        assert chr(0x200B) not in wrapped
        assert "helloworld" in wrapped

    def test_router_prompt_body_is_actually_sanitized_end_to_end(self):
        """This module's own LLM-path prompt construction (`wrap_untrusted` around the
        user message/catalog text) must inherit the same stripping — exercised here at
        the shared `prompt_safety` boundary since select_skills doesn't expose its
        internal prompt text directly."""
        smuggled_message = "please help" + chr(0xE0001) + chr(0x2066)
        wrapped = prompt_safety.wrap_untrusted("user_message", smuggled_message)
        assert chr(0xE0001) not in wrapped
        assert chr(0x2066) not in wrapped


# ---------------------------------------------------------------------------
# Regression guard: _fallback must never dispatch through an executor/thread pool
# ---------------------------------------------------------------------------


class TestFallbackNeverUsesAnExecutor:
    """The H1 finding from a prior review round: routing score_skills through
    `asyncio.to_thread` (or any other executor) would share this repo's default
    ThreadPoolExecutor with every sync `@tool`, including 60-180s sandbox tools —
    starving the router's own fallback of last resort under load. Guard this
    structurally so a future refactor can't silently regress it."""

    def test_fallback_source_contains_no_executor_or_thread_dispatch(self):
        """Inspects the function's *executable body*, not its docstring — the
        docstring deliberately documents this exact anti-pattern by name ("Deliberately
        does NOT use `asyncio.to_thread`...") as the rationale for the guard, so a naive
        substring scan of the whole source (including the docstring) would false-positive
        on the very sentence explaining why the code doesn't do this."""
        source = inspect.getsource(_fallback)
        tree = ast.parse(source)
        func_node = tree.body[0]
        assert isinstance(func_node, ast.AsyncFunctionDef)

        body_stmts = func_node.body
        # Drop the leading docstring Expr node, if present, before reconstructing the
        # executable body's source text.
        if (
            body_stmts
            and isinstance(body_stmts[0], ast.Expr)
            and isinstance(getattr(body_stmts[0], "value", None), ast.Constant)
            and isinstance(body_stmts[0].value.value, str)
        ):
            body_stmts = body_stmts[1:]

        body_only = "\n".join(ast.get_source_segment(source, stmt) or "" for stmt in body_stmts)

        # Sanity check: the docstring's own warning sentence must indeed have been
        # excluded, otherwise this test isn't actually testing what it claims to.
        assert "to_thread" not in body_only

        forbidden_substrings = (
            "to_thread",
            "run_in_executor",
            "ThreadPoolExecutor",
            "concurrent.futures",
            "loop.run_in_executor",
        )
        for forbidden in forbidden_substrings:
            assert forbidden not in body_only, (
                f"_fallback's executable body must never dispatch through an "
                f"executor/thread pool (found {forbidden!r} in its body, outside the "
                f"docstring)"
            )

    @pytest.mark.asyncio
    async def test_fallback_runs_score_skills_inline_on_the_calling_task(self, monkeypatch):
        """Indirect behavioural confirmation: score_skills runs synchronously inline —
        a monkeypatched score_skills that asserts it's on the same running task proves
        no thread/executor hop occurred."""
        import services.skill_router_service as router_module

        calling_task = asyncio.current_task()
        observed = {}

        def _spy_score_skills(catalog, user_message):
            observed["task"] = asyncio.current_task()
            return []

        monkeypatch.setattr(router_module, "score_skills", _spy_score_skills)

        await _fallback([SkillMeta(1, "Alpha")], "alpha")

        # A clear diagnostic instead of an unhelpful KeyError if the hop is hidden in a
        # helper function and the spy never actually ran.
        assert "task" in observed, "score_skills never ran on the event loop — executor hop?"
        assert observed["task"] is calling_task


# ---------------------------------------------------------------------------
# _bind_router_timeout — best-effort defense-in-depth, never fatal
# ---------------------------------------------------------------------------


class TestBindRouterTimeout:
    def test_non_pydantic_llm_double_returned_unchanged(self):
        llm = RunnableLambda(lambda x: x)
        assert _bind_router_timeout(llm) is llm

    def test_plain_object_without_model_fields_returned_unchanged(self):
        class NotAModel:
            pass

        obj = NotAModel()
        assert _bind_router_timeout(obj) is obj
