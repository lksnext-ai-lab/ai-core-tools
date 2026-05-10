"""
Unit tests — SkillRouterService (Phase 5, step 5.1)
===================================================

Verification criteria:
  1. Empty catalog returns empty selection.
  2. All-disabled catalog returns empty selection.
  3. Keyword match selects at most MAX_AUTO_SELECTED skills.
  4. disable_model_invocation skills are excluded even if they match keywords.
  5. Empty message list returns empty selection.
  6. Exceptions inside _select_skills are caught; empty selection returned.
  7. _extract_last_user_text handles str content, list content, and missing role.
  8. _keyword_score returns 0 for short words and > 0 for matching long words.
  9. when_to_use text participates in scoring.
"""

from __future__ import annotations

import pytest
from types import SimpleNamespace
from unittest.mock import patch


def _item(
    name: str,
    description: str = "",
    when_to_use: str | None = None,
    disable_model_invocation: bool = False,
    skill_id: int = 1,
) -> dict:
    return {
        "skill_id": skill_id,
        "name": name,
        "description": description,
        "when_to_use": when_to_use,
        "disable_model_invocation": disable_model_invocation,
    }


def _msg(role: str, content: str) -> dict:
    return {"role": role, "content": content}


# ---------------------------------------------------------------------------
# SkillRouterService.route
# ---------------------------------------------------------------------------


class TestSkillRouterServiceRoute:
    def test_empty_catalog(self):
        from services.skill_router_service import SkillRouterService

        decision = SkillRouterService().route([_msg("user", "hello")], [])
        assert decision["selected_skill_names"] == []

    def test_all_disabled(self):
        from services.skill_router_service import SkillRouterService

        catalog = [_item("disabled-skill", disable_model_invocation=True)]
        decision = SkillRouterService().route([_msg("user", "hello")], catalog)
        assert decision["selected_skill_names"] == []

    def test_keyword_match(self):
        from services.skill_router_service import SkillRouterService

        catalog = [
            _item("charts", description="create charts and graphs", skill_id=1),
            _item("reporting", description="generate reports", skill_id=2),
        ]
        decision = SkillRouterService().route([_msg("user", "create some charts")], catalog)
        assert "charts" in decision["selected_skill_names"]

    def test_max_auto_selected(self):
        from services.skill_router_service import SkillRouterService

        catalog = [
            _item("alpha", description="alpha reporting data", skill_id=1),
            _item("beta", description="beta reporting data", skill_id=2),
            _item("gamma", description="gamma reporting data", skill_id=3),
        ]
        decision = SkillRouterService().route(
            [_msg("user", "generate reporting data")], catalog
        )
        assert len(decision["selected_skill_names"]) <= SkillRouterService.MAX_AUTO_SELECTED

    def test_disabled_skill_excluded_even_if_matching(self):
        from services.skill_router_service import SkillRouterService

        catalog = [
            _item("secret-skill", description="charts graphs", disable_model_invocation=True),
            _item("public-skill", description="simple notes", disable_model_invocation=False),
        ]
        decision = SkillRouterService().route([_msg("user", "make charts")], catalog)
        assert "secret-skill" not in decision["selected_skill_names"]

    def test_no_messages(self):
        from services.skill_router_service import SkillRouterService

        catalog = [_item("charts", description="create charts")]
        decision = SkillRouterService().route([], catalog)
        assert decision["selected_skill_names"] == []

    def test_exception_returns_empty(self):
        from services.skill_router_service import SkillRouterService

        router = SkillRouterService()
        with patch.object(router, "_select_skills", side_effect=RuntimeError("boom")):
            decision = router.route([_msg("user", "hello")], [_item("x")])
        assert decision["selected_skill_names"] == []
        assert "router error" in decision["reason"]

    def test_no_match_returns_empty(self):
        from services.skill_router_service import SkillRouterService

        catalog = [_item("python-scripting", description="write python scripts")]
        decision = SkillRouterService().route([_msg("user", "hi")], catalog)
        assert decision["selected_skill_names"] == []

    @pytest.mark.asyncio
    async def test_llm_route_selects_from_catalog_only(self):
        from services.skill_router_service import SkillRouterService

        class FakeLLM:
            async def ainvoke(self, prompt: str):
                assert "Full conversation" not in prompt
                return SimpleNamespace(
                    content=(
                        '{"selected_skill_names":["charts","not-real"],'
                        '"reason":"chart request"}'
                    )
                )

        catalog = [
            _item("charts", description="create charts and graphs", skill_id=1),
            _item("reporting", description="generate reports", skill_id=2),
        ]
        decision = await SkillRouterService().route_with_llm(
            [_msg("user", "create a chart")],
            catalog,
            llm=FakeLLM(),
        )

        assert decision["selected_skill_names"] == ["charts"]
        assert decision["reason"] == "chart request"

    @pytest.mark.asyncio
    async def test_llm_route_falls_back_to_keywords_on_error(self):
        from services.skill_router_service import SkillRouterService

        class BrokenLLM:
            async def ainvoke(self, _prompt: str):
                raise RuntimeError("nope")

        catalog = [_item("charts", description="create charts and graphs")]
        decision = await SkillRouterService().route_with_llm(
            [_msg("user", "create charts")],
            catalog,
            llm=BrokenLLM(),
        )

        assert decision["selected_skill_names"] == ["charts"]
        assert "keyword fallback" in decision["reason"]

    @pytest.mark.asyncio
    async def test_llm_empty_selection_is_respected(self):
        from services.skill_router_service import SkillRouterService

        class EmptyLLM:
            async def ainvoke(self, _prompt: str):
                return SimpleNamespace(
                    content='{"selected_skill_names":[],"reason":"not a skill task"}'
                )

        catalog = [_item("charts", description="create charts and graphs")]
        decision = await SkillRouterService().route_with_llm(
            [_msg("user", "create charts")],
            catalog,
            llm=EmptyLLM(),
        )

        assert decision["selected_skill_names"] == []
        assert decision["reason"] == "not a skill task"


# ---------------------------------------------------------------------------
# SkillToolRouterService
# ---------------------------------------------------------------------------


class TestSkillToolRouterService:
    @pytest.mark.asyncio
    async def test_routes_selected_skill_to_available_tool(self):
        from services.skill_router_service import (
            SkillToolRouterService,
            format_skill_tool_guidance_section,
        )

        class FakeLLM:
            async def ainvoke(self, prompt: str):
                assert "PptxGenJS" in prompt
                assert "typescript_repl" in prompt
                return SimpleNamespace(
                    content=(
                        '{"instructions":"Use TypeScript for PPTX construction.",'
                        '"tool_guidance":[{"skill_name":"pptx",'
                        '"operation":"create presentation with PptxGenJS",'
                        '"preferred_tool":"typescript_repl",'
                        '"fallback_tools":["bash_repl"],'
                        '"reason":"PptxGenJS is a Node/TypeScript library."}]}'
                    )
                )

        decision = await SkillToolRouterService().route_with_llm(
            selected_skills=[
                {
                    "name": "pptx",
                    "description": "PowerPoint generation",
                    "instructions": "Use PptxGenJS to create presentations.",
                }
            ],
            available_tools=[
                {"name": "typescript_repl", "description": "Run TypeScript."},
                {"name": "bash_repl", "description": "Run shell commands."},
            ],
            llm=FakeLLM(),
        )

        assert decision is not None
        assert decision["tool_guidance"][0]["preferred_tool"] == "typescript_repl"
        section = format_skill_tool_guidance_section(decision)
        assert "prefer `typescript_repl`" in section
        assert "fallback: `bash_repl`" in section

    @pytest.mark.asyncio
    async def test_rejects_unknown_skill_and_tool_names(self):
        from services.skill_router_service import SkillToolRouterService

        class FakeLLM:
            async def ainvoke(self, _prompt: str):
                return SimpleNamespace(
                    content=(
                        '{"instructions":"x",'
                        '"tool_guidance":[{"skill_name":"other",'
                        '"operation":"x","preferred_tool":"missing_tool",'
                        '"fallback_tools":["bash_repl"],"reason":"x"}]}'
                    )
                )

        decision = await SkillToolRouterService().route_with_llm(
            selected_skills=[{"name": "pptx", "instructions": "Use PptxGenJS."}],
            available_tools=[{"name": "typescript_repl"}],
            llm=FakeLLM(),
        )

        assert decision is None

    @pytest.mark.asyncio
    async def test_tool_router_failure_returns_none(self):
        from services.skill_router_service import SkillToolRouterService

        class BrokenLLM:
            async def ainvoke(self, _prompt: str):
                raise RuntimeError("boom")

        decision = await SkillToolRouterService().route_with_llm(
            selected_skills=[{"name": "pptx", "instructions": "Use PptxGenJS."}],
            available_tools=[{"name": "typescript_repl"}],
            llm=BrokenLLM(),
        )

        assert decision is None


# ---------------------------------------------------------------------------
# _extract_last_user_text
# ---------------------------------------------------------------------------


class TestExtractLastUserText:
    def test_str_content(self):
        from services.skill_router_service import _extract_last_user_text

        msgs = [_msg("user", "Hello World")]
        assert _extract_last_user_text(msgs) == "hello world"

    def test_list_content(self):
        from services.skill_router_service import _extract_last_user_text

        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Make me a Chart"},
                    {"type": "image_url", "image_url": {"url": "data:..."}},
                ],
            }
        ]
        result = _extract_last_user_text(msgs)
        assert "make me a chart" in result

    def test_last_user_message_used(self):
        from services.skill_router_service import _extract_last_user_text

        msgs = [
            _msg("user", "First message"),
            _msg("assistant", "Some response"),
            _msg("user", "Second message"),
        ]
        assert _extract_last_user_text(msgs) == "second message"

    def test_no_user_message(self):
        from services.skill_router_service import _extract_last_user_text

        msgs = [_msg("assistant", "Hello")]
        assert _extract_last_user_text(msgs) == ""

    def test_empty_list(self):
        from services.skill_router_service import _extract_last_user_text

        assert _extract_last_user_text([]) == ""


# ---------------------------------------------------------------------------
# _keyword_score
# ---------------------------------------------------------------------------


class TestKeywordScore:
    def test_returns_zero_for_short_words(self):
        from services.skill_router_service import _keyword_score

        # Words 3 chars or fewer are ignored
        skill = _item("to", description="do it")
        score = _keyword_score("do it", skill)
        assert score == 0

    def test_returns_positive_for_matching_word(self):
        from services.skill_router_service import _keyword_score

        skill = _item("charts", description="generate charts")
        score = _keyword_score("generate some charts please", skill)
        assert score > 0

    def test_when_to_use_participates(self):
        from services.skill_router_service import _keyword_score

        skill = _item("reporter", when_to_use="use when analysing financial documents")
        score = _keyword_score("analysing financial documents", skill)
        assert score > 0

    def test_no_overlap_returns_zero(self):
        from services.skill_router_service import _keyword_score

        skill = _item("charts", description="generate visualisations")
        assert _keyword_score("write a poem about autumn", skill) == 0
