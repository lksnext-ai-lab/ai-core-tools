"""
SkillRouterService — metadata-only Skill pre-selection before main LLM turn.

Selects up to MAX_AUTO_SELECTED skills by keyword scoring against the incoming
user message without making any LLM call.  Safe-defaults to an empty selection
on any error so downstream behaviour is unaffected.
"""
from __future__ import annotations

from typing import Any
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TypedDict-like dicts
# ---------------------------------------------------------------------------

class SkillRouteDecision(dict):
    """Keys: selected_skill_names (list[str]), reason (str)."""


class SkillCatalogItem(dict):
    """Keys: skill_id (int), name (str), description (str),
    when_to_use (str|None), disable_model_invocation (bool)."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class SkillRouterService:
    """Metadata-only skill pre-selector.

    Usage::

        router = SkillRouterService()
        decision = router.route(user_messages, catalog)
        selected = set(decision["selected_skill_names"])
    """

    MAX_AUTO_SELECTED: int = 2

    def route(
        self,
        user_messages: list[dict],
        skill_catalog: list[SkillCatalogItem],
    ) -> SkillRouteDecision:
        """Select at most MAX_AUTO_SELECTED skills for the current turn.

        Skills with ``disable_model_invocation=True`` are filtered out before
        scoring — they are never shown in the system prompt.

        Returns an empty selection on any error (safe default).
        """
        if not skill_catalog:
            return SkillRouteDecision(selected_skill_names=[], reason="no match")

        eligible = [s for s in skill_catalog if not s.get("disable_model_invocation", False)]
        if not eligible:
            return SkillRouteDecision(selected_skill_names=[], reason="no eligible skills")

        try:
            return self._select_skills(user_messages, eligible)
        except Exception as exc:
            logger.warning(
                "SkillRouterService.route failed: %s — returning empty selection.", exc
            )
            return SkillRouteDecision(
                selected_skill_names=[],
                reason=f"router error: {exc}",
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _select_skills(
        self,
        user_messages: list[dict],
        eligible: list[SkillCatalogItem],
    ) -> SkillRouteDecision:
        if not user_messages:
            return SkillRouteDecision(selected_skill_names=[], reason="no messages")

        last_user_content = _extract_last_user_text(user_messages)
        if not last_user_content:
            return SkillRouteDecision(selected_skill_names=[], reason="no user message")

        scored: list[tuple[int, str]] = []
        for skill in eligible:
            score = _keyword_score(last_user_content, skill)
            if score > 0:
                scored.append((score, skill["name"]))

        scored.sort(reverse=True)
        selected = [name for _, name in scored[: self.MAX_AUTO_SELECTED]]

        if not selected:
            return SkillRouteDecision(selected_skill_names=[], reason="no match")

        return SkillRouteDecision(
            selected_skill_names=selected,
            reason=f"keyword match: {selected}",
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _extract_last_user_text(messages: list[dict]) -> str:
    """Return the lowercased text of the last user message, or empty string."""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content.lower()
            if isinstance(content, list):
                return " ".join(
                    part.get("text", "")
                    for part in content
                    if part.get("type") == "text"
                ).lower()
    return ""


def _keyword_score(user_text: str, skill: SkillCatalogItem) -> int:
    """Return a simple keyword overlap score between *user_text* and *skill* metadata."""
    target_text = " ".join(
        filter(
            None,
            [
                skill.get("name", ""),
                skill.get("description", ""),
                skill.get("when_to_use") or "",
            ],
        )
    ).lower()

    score = 0
    for word in user_text.split():
        if len(word) > 3 and word in target_text:
            score += 1
    return score
